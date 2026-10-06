import pytest

from jobscan import doctor

SECRET_ID, SECRET_KEY, SECRET_RAPID = "id-12345", "adzkey-SECRET", "rapid-SECRET"


@pytest.fixture
def env(monkeypatch, tmp_path):
    (tmp_path / "profiles/p").mkdir(parents=True)
    (tmp_path / "profiles/p/profile.yaml").write_text("display_name: P\n")
    (tmp_path / "config.yaml").write_text("sources:\n  jsearch: {auth: proxy}\n")
    for n in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY", "RAPIDAPI_KEY"):
        monkeypatch.delenv(n, raising=False)
    return tmp_path


def fake(monkeypatch, status, payload=None, error=""):
    sent = []
    def probe(url, params=None, headers=None, timeout=20):
        sent.append({"url": url, "params": params or {}, "headers": headers or {}})
        return status, payload, error
    monkeypatch.setattr(doctor, "probe_json", probe)
    return sent


def test_everything_ok_exits_zero_and_never_prints_a_key(env, monkeypatch, capsys):
    monkeypatch.setenv("ADZUNA_APP_ID", SECRET_ID); monkeypatch.setenv("ADZUNA_APP_KEY", SECRET_KEY)
    monkeypatch.setenv("RAPIDAPI_KEY", SECRET_RAPID)
    fake(monkeypatch, 200, {"results": [1], "data": [1, 2]})
    assert doctor.main(["--data", str(env)]) == 0
    out = capsys.readouterr().out
    assert "adzuna   OK, HTTP 200, 1 result(s)" in out and "jsearch  OK, HTTP 200, 2 result(s)" in out
    assert not any(s in out for s in (SECRET_ID, SECRET_KEY, SECRET_RAPID))


def test_missing_adzuna_variables_are_named(env, capsys):
    ok, msg = doctor.check_adzuna()
    assert not ok and "ADZUNA_APP_ID, ADZUNA_APP_KEY" in msg


def test_jsearch_via_proxy_sends_no_key_header(env, monkeypatch):
    sent = fake(monkeypatch, 200, {"data": []})
    ok, msg = doctor.check_jsearch(via_proxy=True)
    assert ok and "credential proxy" in msg
    assert "X-RapidAPI-Key" not in sent[0]["headers"] and sent[0]["headers"]["X-RapidAPI-Host"]


def test_jsearch_without_key_or_proxy_is_not_set(env):
    ok, msg = doctor.check_jsearch(via_proxy=False)
    assert not ok and msg.startswith("NOT SET: RAPIDAPI_KEY")


@pytest.mark.parametrize("status, error, needle", [
    (401, "HTTPError", "key was rejected"), (403, "HTTPError", "credential does not match"),
    (429, "HTTPError", "quota or rate limit"), (None, "URLError", "Allowed domains"),
    (500, "HTTPError", "unexpected response")])
def test_failures_say_what_to_do(env, monkeypatch, status, error, needle):
    monkeypatch.setenv("ADZUNA_APP_ID", "i"); monkeypatch.setenv("ADZUNA_APP_KEY", "k")
    fake(monkeypatch, status, None, error)
    ok, msg = doctor.check_adzuna()
    assert not ok and needle in msg


def test_any_failure_exits_one(env, monkeypatch, capsys):
    monkeypatch.setenv("ADZUNA_APP_ID", "i"); monkeypatch.setenv("ADZUNA_APP_KEY", "k")
    fake(monkeypatch, 429)
    assert doctor.main(["--data", str(env)]) == 1
