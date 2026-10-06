import pytest

from jobscan import collect
from jobscan.sources import adzuna, jsearch

Q = {"query": "java"}


@pytest.fixture
def calls(monkeypatch):
    seen = []
    def fake(url, params=None, headers=None, timeout=20):
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
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    cfg = {"profiles": [], "sources": {"jsearch": {"access_method": "keyed_api", "auth": "proxy"},
                                       "adzuna": {"access_method": "keyed_api"}}}
    assert collect.proxied_sources(cfg) == {"jsearch"}
    lines = collect.preflight(tmp_path, cfg)
    assert "  RAPIDAPI_KEY: added by the credential proxy (not checked here)" in lines
    assert "  ADZUNA_APP_KEY: missing" in lines
    lines = collect.preflight(tmp_path, {"profiles": []})
    assert "  RAPIDAPI_KEY: missing" in lines
