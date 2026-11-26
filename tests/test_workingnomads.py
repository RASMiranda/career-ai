"""Working Nomads adapter (ADR-080). Recorded-shape fixture only, no network: the fixture is
hand-trimmed, see tests/fixtures/workingnomads/README.md."""

import json
from pathlib import Path

import pytest

from jobscan.sources import workingnomads

FIXTURE = Path(__file__).parent / "fixtures" / "workingnomads" / "exposed_jobs.json"


@pytest.fixture(autouse=True)
def fresh_feed():
    workingnomads.reset_cache()
    yield
    workingnomads.reset_cache()


@pytest.fixture
def feed(monkeypatch):
    """Serves the fixture as the feed and records every request made."""
    calls = []
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def fake(url, params=None, headers=None, timeout=20, retries=0):
        calls.append(url)
        return data
    monkeypatch.setattr(workingnomads, "get_json", fake)
    return calls


def titles(rows):
    return [c.title for c in rows]


def test_substring_matches_title_tags_and_description(feed):
    def q(text):
        return titles(workingnomads.fetch({"query": text}, "p"))
    assert q("java") == ["Senior Java Developer", "Data Analyst"]   # title and tags, then description only
    assert q("angular") == ["Frontend Engineer"]                    # tags and description
    assert q("spring") == ["Senior Java Developer", "Platform Lead"]
    assert q("spring boot") == ["Platform Lead"]
    assert q("ANGULAR") == ["Frontend Engineer"]                    # case-insensitive
    assert q("rust") == []                                          # no match is an empty list, not an error


def test_the_feed_is_fetched_once_for_several_queries(feed):
    for text in ("java", "spring", "angular", "rust"):
        workingnomads.fetch({"query": text}, "p")
    assert len(feed) == 1


def test_candidate_fields_come_from_the_feed(feed):
    (cand,) = workingnomads.fetch({"query": "angular"}, "p")
    assert cand.source == "workingnomads"
    assert cand.remote is True
    assert cand.url == "https://www.workingnomads.com/jobs/example-frontend-engineer"
    assert cand.posted_at == "2026-11-21T14:30:00+01:00"
    assert cand.location == "Europe" and cand.company == "Sample Web"
    assert cand.contract_type == "" and cand.salary == ""   # absent in the feed, so absent here
    assert "<p>" not in cand.description                     # HTML is stripped before the model sees it
    assert len(cand.candidate_key) == 16


def test_a_feed_failure_is_an_error_and_is_requested_once(monkeypatch):
    calls = []
    monkeypatch.setattr(workingnomads, "get_json", lambda url, *a, **k: calls.append(url))
    for text in ("java", "spring"):
        with pytest.raises(ConnectionError):
            workingnomads.fetch({"query": text}, "p")
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [{"jobs": []}, "not a feed", 42])
def test_a_feed_that_is_not_an_array_is_an_error(monkeypatch, payload):
    monkeypatch.setattr(workingnomads, "get_json", lambda *a, **k: payload)
    with pytest.raises(ConnectionError):
        workingnomads.fetch({"query": "java"}, "p")


def test_rows_without_title_or_company_are_skipped(monkeypatch):
    rows = [{"title": "", "company_name": "Co", "tags": "java"},
            {"title": "Java Dev", "company_name": "", "tags": "java"},
            {"title": "Java Dev", "company_name": "Co", "tags": "java", "url": "https://example.test/ok"}]
    monkeypatch.setattr(workingnomads, "get_json", lambda *a, **k: rows)
    assert [c.url for c in workingnomads.fetch({"query": "java"}, "p")] == ["https://example.test/ok"]
