import urllib.parse

import pytest

from jobscan import feedback, report
from jobscan.apply import summary
from jobscan.apply.queue import Queue

CFG = {"profiles": [{"id": "p", "notify": {"email": ["me@mail.test"]}}]}


def params(url):
    return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}


def test_each_kind_opens_its_own_issue_form_prefilled():
    for kind, template in (("bug", "bug.yml"), ("feature", "feature.yml"), ("support", "support.yml")):
        url = feedback.issue_url(kind, title="  something   odd ", context="career-ai 0.1.0 · scan 2026-10-09")
        assert url.startswith("https://github.com/RASMiranda/career-ai/issues/new?")
        got = params(url)
        assert got["template"] == template and got["context"] == "career-ai 0.1.0 · scan 2026-10-09"
        assert got["title"] == feedback.KINDS[kind][1] + "something odd"


def test_the_templates_it_points_at_exist_and_the_prefilled_ids_are_real_form_fields():
    import yaml
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / ".github/ISSUE_TEMPLATE"
    for kind, (template, _, _) in feedback.KINDS.items():
        ids = {b["id"] for b in yaml.safe_load((root / template).read_text())["body"] if "id" in b}
        assert "context" in ids
    bug_ids = {b["id"] for b in yaml.safe_load((root / "bug.yml").read_text())["body"] if "id" in b}
    assert {"what_happened", "context", "redacted_output"} <= bug_ids          # what failure_url pre-fills


def test_the_repository_is_validated_and_can_be_overridden():
    assert feedback.issue_url("bug", "someone/else").startswith("https://github.com/someone/else/issues/new?")
    for bad in ("evil.com/x?y", "a b/c", "../x", "-a/b", "a/..", "x", "a/b/c", "", "a/b?x=1", "a/b#h"):
        with pytest.raises(ValueError):
            feedback.issue_url("bug", bad)


def test_an_oversized_prefill_falls_back_to_the_bare_form():
    url = feedback.issue_url("bug", title="t", what_happened="x" * 5000, redacted_output="y" * 5000, context="c")
    assert url == "https://github.com/RASMiranda/career-ai/issues/new?template=bug.yml"


def failed(**o):
    return {"title": "Secret Role", "company": "SecretCorp", "url": "https://jobs.lever.co/secretcorp/abc-123?x=1",
            "status": "failed", "error_code": "UNKNOWN_REQUIRED_FIELD", "candidate_key": "k" * 16, "fit": 90, "profile": "p",
            "cv": "general", "error_message": "3 required field(s) like Salary expectations", **o}


def test_a_failure_link_carries_the_code_the_site_and_nothing_personal():
    url = feedback.failure_url(failed())
    got = params(url)
    assert got["template"] == "bug.yml" and "UNKNOWN_REQUIRED_FIELD" in got["title"]
    assert "jobs.lever.co" in got["what_happened"] and "UNKNOWN_REQUIRED_FIELD" in got["what_happened"]
    blob = urllib.parse.unquote(url).lower()
    for private in ("secretcorp", "secret role", "abc-123", "salary", "general", "k" * 16):
        assert private not in blob, private


def test_a_hostile_error_code_is_not_passed_through():
    got = params(feedback.failure_url(failed(error_code="X</a><script>alert(1)</script>")))
    assert "script" not in got["what_happened"] and "INTERNAL" in got["what_happened"]


def test_the_email_ends_with_the_three_links_and_a_privacy_note(tmp_path):
    html = report.render_email("2026-10-09", [], [])
    for label in ("Report a problem", "Suggest a feature", "Ask for help"):
        assert label in html
    assert html.count("github.com/RASMiranda/career-ai/issues/new") == 3
    assert "&amp;" in html and "nothing personal" in html.lower()                  # attribute ampersands are escaped
    assert "Do not paste names" in html


def test_the_repository_comes_from_config_when_it_is_set(tmp_path):
    q = Queue(tmp_path)
    q.add("fail000001", {"title": "T", "company": "C", "url": "https://jobs.lever.co/c/1", "status": "failed",
                         "error_code": "CAPTCHA", "fit": 80, "profile": "p"})
    cfg = {**CFG, "feedback": {"repo": "me/my-fork"}}
    out = tmp_path / "o"
    out.mkdir()
    [d] = report.build_deliveries("2026-10-09", cfg, {"candidates": []}, [], q, out)
    body = open(d["body"]).read()
    assert body.count("github.com/me/my-fork/issues/new") == 4                    # three footer links + the failure's own
    assert "RASMiranda/career-ai/issues" not in body


def test_each_failed_application_in_the_email_has_a_report_link_that_exposes_nothing(tmp_path):
    q = Queue(tmp_path)
    q.add("fail000001", {**failed(), "candidate_key": "fail000001"})
    block = summary.render_failures(q, "p")
    assert "Report this failure" in block and "issues/new?template=bug.yml" in block
    assert "SecretCorp" in block                                                  # visible to its owner in the email
    href = block.split('href="')[2].split('"')[0]
    assert "secretcorp" not in urllib.parse.unquote(href.replace("&amp;", "&")).lower()


def test_cli_prints_the_url_and_can_open_it(capsys, monkeypatch):
    opened = []
    monkeypatch.setattr(feedback.webbrowser, "open", lambda url: opened.append(url) or True)
    assert feedback.main(["feature", "--title", "dark mode", "--open"]) == 0
    printed = capsys.readouterr().out.strip()
    assert opened == [printed] and params(printed)["template"] == "feature.yml"
    assert feedback.main(["--repo", "nope"]) == 2 and "not a GitHub repository" in capsys.readouterr().err
    monkeypatch.setattr(feedback.webbrowser, "open", lambda url: False)
    assert feedback.main(["bug", "--open"]) == 0 and "could not open a browser" in capsys.readouterr().err
