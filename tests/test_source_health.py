"""SourceHealth in the collector, the report and the email (ARCHITECTURE §2b, ADR-080), and the
terms gate for declared sources. No network: every source is a fake."""

import json

import pytest
import yaml

from jobscan import collect, report
from jobscan.models import Candidate
from jobscan.sources import MANIFESTS, REGISTRY, blocked_reason, manifest_gaps
from profile_helpers import ensure_profile


def cand(source, n):
    return Candidate(candidate_key=f"{source}-{n}", profile="p", source=source, title=f"Job {n}",
                     company="Co", url=f"https://example.test/{source}/{n}")


def repo(tmp_path, queries):
    (tmp_path / "config.yaml").write_text("sources: {}\n", encoding="utf-8")
    folder = ensure_profile(tmp_path)
    (folder / "profile.yaml").write_text(yaml.safe_dump({"daily_queries": queries}), encoding="utf-8")
    return tmp_path


def collect_run(tmp_path, capsys):
    out = tmp_path / "candidates.json"
    assert collect.main(["--data", str(tmp_path), "--out", str(out)]) == 0
    capsys.readouterr()
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.mark.parametrize("outcomes, status", [
    ([3, 0], "ok"),                    # one query returned results: the source is working
    ([0, 0], "empty-unexpectedly"),    # every query ran and returned nothing
    ([0, "failed"], "failed"),         # a query raised and nothing came back
    (["failed"], "failed"),
    (["not-run"], "not-run"),
    (["not-run", 0], "empty-unexpectedly"),
])
def test_source_health_rules(outcomes, status):
    assert collect.source_health(outcomes) == status


def test_a_configured_source_with_zero_results_is_visible(tmp_path, monkeypatch, capsys):
    repo(tmp_path, [{"source": "arbeitnow", "query": "java spring"},
                    {"source": "remotive", "query": "java", "limit": 40}])
    monkeypatch.setitem(REGISTRY, "arbeitnow", lambda q, p, s=None: [])
    monkeypatch.setitem(REGISTRY, "remotive", lambda q, p, s=None: [cand("remotive", 1)])
    payload = collect_run(tmp_path, capsys)
    assert payload["source_health"] == {"arbeitnow": "empty-unexpectedly", "remotive": "ok"}
    assert payload["counts"]["new"] == 1


def test_a_failing_source_is_failed_and_recorded_as_an_error(tmp_path, monkeypatch, capsys):
    repo(tmp_path, [{"source": "arbeitnow", "query": "java"}])
    def broken(q, p, s=None):
        raise RuntimeError("boom")
    monkeypatch.setitem(REGISTRY, "arbeitnow", broken)
    payload = collect_run(tmp_path, capsys)
    assert payload["source_health"] == {"arbeitnow": "failed"}
    assert "arbeitnow: RuntimeError" in payload["errors"]


def test_a_source_whose_terms_are_not_reviewed_is_never_called(tmp_path, monkeypatch, capsys):
    repo(tmp_path, [{"source": "workingnomads", "query": "java"}])
    called = []
    monkeypatch.setitem(REGISTRY, "workingnomads", lambda q, p, s=None: called.append(q) or [cand("workingnomads", 1)])
    payload = collect_run(tmp_path, capsys)
    assert called == []
    assert payload["source_health"] == {"workingnomads": "not-run"}
    assert any("workingnomads: terms not reviewed (ADR-080)" in e for e in payload["errors"])
    assert payload["counts"]["new"] == 0


def test_the_terms_gate_and_manifests():
    assert blocked_reason("workingnomads") is not None
    assert blocked_reason("remotive") is None
    assert blocked_reason("arbeitnow") is None   # undeclared: not gated here (see sources/__init__.py)
    for name in ("remotive", "workingnomads"):
        assert manifest_gaps(name) == [], name
        assert MANIFESTS[name]["access_method"] == "public_api"
    assert MANIFESTS["remotive"]["redistribution_allowed"] is False
    assert MANIFESTS["workingnomads"]["terms_reviewed"] is None


def test_the_registry_has_the_new_and_existing_sources():
    assert {"remotive", "workingnomads"} <= set(REGISTRY)
    assert "jobgether" not in REGISTRY   # waits for the owner's sample (ADR-081)


def test_health_text_names_every_source_and_escapes_html():
    assert report.health_text(None) == ""
    text = report.health_text({"remotive": "ok", "arbeitnow": "empty-unexpectedly"})
    assert text == "Sources: arbeitnow empty-unexpectedly · remotive ok"
    html = report.render_email("2026-11-26", [], [], health={"<x>": "failed"})
    assert "Sources: &lt;x&gt; failed" in html
    assert "Sources:" not in report.render_email("2026-11-26", [], [])
    assert "Sources: remotive ok" in report.render_markdown("2026-11-26", [], [], [], {"remotive": "ok"})
