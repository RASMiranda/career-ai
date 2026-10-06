import pytest

from jobscan import collect
from jobscan.sources import adzuna, jsearch

Q = {"query": "java"}


@pytest.fixture
def calls(monkeypatch):
    seen = []
    def fake(url, params=None, headers=None, timeout=20, retries=0):
        seen.append({"url": url, "headers": headers or {}})
        return {"data": [], "results": []}
    monkeypatch.setattr(jsearch, "get_json", fake)
    monkeypatch.setattr(adzuna, "get_json", fake)
    return seen


def test_jsearch_without_a_key_is_skipped(calls):
    assert jsearch.fetch(Q, "p", {}) == [] and calls == []


def test_jsearch_with_an_env_key_sends_it(calls):
    jsearch.fetch(Q, "p", {"RAPIDAPI_KEY": "k"})
    assert calls[0]["headers"]["X-RapidAPI-Key"] == "k"
    assert calls[0]["headers"]["X-RapidAPI-Host"] == "jsearch.p.rapidapi.com"


def test_jsearch_with_proxy_auth_sends_no_key_itself(calls):
    jsearch.fetch(Q, "p", {"_proxy": {"jsearch"}})
    assert "X-RapidAPI-Key" not in calls[0]["headers"]
    assert calls[0]["headers"]["X-RapidAPI-Host"] == "jsearch.p.rapidapi.com"


def test_jsearch_falls_back_to_the_older_endpoint(monkeypatch):
    tried = []
    def fake(url, params=None, headers=None, timeout=20, retries=0):
        tried.append(url)
        return None if url.endswith("/search-v2") else {"data": []}
    monkeypatch.setattr(jsearch, "get_json", fake)
    assert jsearch.fetch(Q, "p", {"RAPIDAPI_KEY": "k"}) == []
    assert [u.rsplit("/", 1)[1] for u in tried] == ["search-v2", "search"]


@pytest.mark.parametrize("data", [
    [{"job_id": "1", "job_title": "Java Dev", "employer_name": "Acme"}],
    {"jobs": [{"job_id": "1", "job_title": "Java Dev", "employer_name": "Acme"}], "cursor": "c"},
])
def test_jsearch_reads_both_response_shapes(monkeypatch, data):
    monkeypatch.setattr(jsearch, "get_json", lambda *a, **k: {"status": "OK", "data": data})
    out = jsearch.fetch(Q, "p", {"RAPIDAPI_KEY": "k"})
    assert [c.title for c in out] == ["Java Dev"]


@pytest.mark.parametrize("fn, secrets", [
    (jsearch.fetch, {"RAPIDAPI_KEY": "k"}),
    (adzuna.fetch, {"ADZUNA_APP_ID": "i", "ADZUNA_APP_KEY": "k"}),
])
def test_a_failed_call_is_an_error_not_silence(monkeypatch, fn, secrets):
    monkeypatch.setattr(jsearch, "get_json", lambda *a, **k: None)
    monkeypatch.setattr(adzuna, "get_json", lambda *a, **k: None)
    with pytest.raises(ConnectionError):
        fn({"query": "java", "country": "pt"}, "p", secrets)


def test_adzuna_without_keys_is_skipped(calls):
    assert adzuna.fetch(Q, "p", {"ADZUNA_APP_ID": "i"}) == [] and calls == []


def test_proxied_sources_and_preflight(tmp_path, monkeypatch):
    for var in ("RAPIDAPI_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY"):
        monkeypatch.delenv(var, raising=False)
    cfg = {"profiles": [], "sources": {"jsearch": {"access_method": "keyed_api", "auth": "proxy"},
                                       "adzuna": {"access_method": "keyed_api"}}}
    assert collect.proxied_sources(cfg) == {"jsearch"}
    lines = collect.preflight(tmp_path, cfg)
    assert "  RAPIDAPI_KEY: added by the credential proxy (not checked here)" in lines
    assert "  ADZUNA_APP_KEY: missing" in lines
    lines = collect.preflight(tmp_path, {"profiles": []})
    assert "  RAPIDAPI_KEY: missing" in lines


def test_jsearch_falls_back_to_the_older_endpoint(monkeypatch):
    tried = []
    def fake(url, params=None, headers=None, timeout=20, retries=0):
        tried.append(url.rsplit("/", 1)[1])
        return None if url.endswith("/search-v2") else {"data": []}
    monkeypatch.setattr(jsearch, "get_json", fake)
    jsearch.fetch(Q, "p", {"RAPIDAPI_KEY": "k"})
    assert tried == ["search-v2", "search"]


def test_jsearch_v2_nested_jobs_are_parsed(monkeypatch):
    job = {"job_id": "1", "job_title": "Dev", "employer_name": "Acme"}
    monkeypatch.setattr(jsearch, "get_json", lambda *a, **k: {"data": {"jobs": [job], "cursor": "x"}})
    out = jsearch.fetch(Q, "p", {"RAPIDAPI_KEY": "k"})
    assert [c.title for c in out] == ["Dev"]


def test_jsearch_waits_longer_and_retries(calls, monkeypatch):
    got = {}
    def fake(url, params=None, headers=None, timeout=20, retries=0):
        got.update(timeout=timeout, retries=retries)
        return {"data": []}
    monkeypatch.setattr(jsearch, "get_json", fake)
    jsearch.fetch(Q, "p", {"RAPIDAPI_KEY": "k"})
    assert got == {"timeout": jsearch.TIMEOUT, "retries": jsearch.RETRIES} and jsearch.TIMEOUT > 20
