import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from jobscan import fetchpage

JOB = ('<html><head><script type="application/ld+json">' + json.dumps({
    "@type": "JobPosting", "title": "Senior Java Lead", "hiringOrganization": {"name": "Acme"},
    "description": "Lead the platform team and mentor developers across the company every day.",
    "url": "https://board.test/jobs/1"}) + "</script></head><body>job</body></html>")


@pytest.fixture
def server():
    seen = []
    pages = {
        "/job": (200, {}, JOB),
        "/plain": (200, {"Set-Cookie": "session=abc"}, "<html><title>x</title>hello</html>"),
        "/forbidden": (403, {}, "no"),
        "/linkedin": (999, {}, "no"),
        "/toomany": (429, {}, "slow down"),
        "/missing": (404, {}, "gone"),
        "/captcha": (200, {}, "<html><div class='g-recaptcha'></div></html>"),
        "/unusual": (200, {}, "<html>We detected Unusual Activity from your network</html>"),
        "/challenge": (200, {}, "<html><title>Just a moment...</title></html>"),
        "/to-authwall": (302, {"Location": "/authwall?trk=x"}, ""),
        "/to-job": (302, {"Location": "/job"}, ""),
        "/loop": (302, {"Location": "/loop"}, ""),
        "/authwall": (200, {}, "Sign in"),
        "/huge": (200, {}, "x" * (fetchpage.MAX_BYTES + 10)),
    }

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            seen.append({"path": self.path.split("?")[0], "ua": self.headers.get("User-Agent"),
                         "cookie": self.headers.get("Cookie")})
            status, headers, body = pages.get(self.path.split("?")[0], (404, {}, "nf"))
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body.encode())

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", seen
    srv.shutdown()


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(fetchpage.time, "sleep", slept.append)
    return slept


def fetch(urls, tmp_path, **kw):
    return fetchpage.fetch_all(urls, tmp_path, allow_local=True, **kw)


def test_a_normal_page_is_saved_with_an_honest_user_agent_and_no_cookies(server, tmp_path):
    base, seen = server
    saved, blocked = fetch([base + "/plain", base + "/plain"], tmp_path)
    assert blocked == "" and len(saved) == 2 and "hello" in saved[0].read_text()
    assert all("career-ai-jobscan" in r["ua"] and "owner's request" in r["ua"] for r in seen)
    assert all(r["cookie"] is None for r in seen)                       # the cookie it was given is never sent back


@pytest.mark.parametrize("path,why", [
    ("/forbidden", "HTTP 403"), ("/linkedin", "HTTP 999"), ("/toomany", "HTTP 429"),
    ("/captcha", "CAPTCHA"), ("/unusual", "unusual"), ("/challenge", "challenge page"),
    ("/to-authwall", "login or challenge page"),
])
def test_the_first_block_signal_stops_the_run_and_the_host_for_the_day(server, tmp_path, path, why):
    base, seen = server
    saved, blocked = fetch([base + "/plain", base + path, base + "/plain"], tmp_path)
    assert why.lower() in blocked.lower() and len(saved) == 1
    assert [r["path"] for r in seen][-1] != "/plain" or len(seen) == 2    # the third URL was never requested
    before = len(seen)
    saved2, blocked2 = fetch([base + "/plain"], tmp_path)
    assert saved2 == [] and "not trying again" in blocked2 and len(seen) == before   # no request at all


def test_a_missing_page_is_not_a_block(server, tmp_path, capsys):
    base, _ = server
    saved, blocked = fetch([base + "/missing", base + "/plain"], tmp_path)
    assert blocked == "" and len(saved) == 1 and "HTTP 404" in capsys.readouterr().err


def test_redirects_are_followed_a_few_hops_and_judged_at_each_one(server, tmp_path, capsys):
    base, _ = server
    saved, blocked = fetch([base + "/to-job"], tmp_path)
    assert blocked == "" and len(saved) == 1 and "Senior Java Lead" in saved[0].read_text()
    saved, blocked = fetch([base + "/loop"], tmp_path / "b")
    assert saved == [] and "redirects" in capsys.readouterr().err


def test_a_page_over_the_size_limit_is_refused(server, tmp_path, capsys):
    base, _ = server
    assert fetch([base + "/huge"], tmp_path)[0] == [] and "larger than" in capsys.readouterr().err


def test_waits_between_requests_and_caps_the_number(server, tmp_path, no_sleep):
    base, _ = server
    fetch([base + "/plain", base + "/job", base + "/plain"], tmp_path, delay=7)
    assert no_sleep == [7, 7]
    with pytest.raises(fetchpage.Refused, match="at most 5"):
        fetch([base + "/plain"] * 6, tmp_path)


@pytest.mark.parametrize("url", ["http://www.linkedin.com/jobs/view/1", "https://localhost/x", "https://127.0.0.1/x",
                                 "https://10.0.0.5/x", "https://169.254.169.254/latest", "https://db.internal/x",
                                 "ftp://x.test/f", "https:///nohost"])
def test_only_public_https_hosts_are_ever_requested(url, tmp_path):
    with pytest.raises(fetchpage.Refused):
        fetchpage.fetch_all([url], tmp_path)


def test_public_https_names_are_accepted():
    assert fetchpage.refuse_reason("https://www.linkedin.com/jobs/view/123") == ""
    assert fetchpage.refuse_reason("https://8.8.8.8/x") == ""


def test_cli_reports_the_clip_verdict_on_each_saved_page(server, tmp_path, capsys, monkeypatch):
    base, _ = server
    monkeypatch.setattr(fetchpage, "refuse_reason", lambda url, allow_local=False: "")
    assert fetchpage.main([base + "/job", base + "/plain", "--out-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "JobPosting found: Senior Java Lead — Acme" in out and "no schema.org JobPosting" in out


def test_cli_exit_codes_and_message_when_blocked(server, tmp_path, capsys, monkeypatch):
    base, _ = server
    monkeypatch.setattr(fetchpage, "refuse_reason", lambda url, allow_local=False: "")
    assert fetchpage.main([base + "/forbidden", "--out-dir", str(tmp_path)]) == 3
    err = capsys.readouterr().err
    assert "BLOCKED" in err and "Nothing was done to get past it" in err and "your own browser" in err
    assert fetchpage.main([base + "/missing", "--out-dir", str(tmp_path / "n")]) == 1


def test_cli_refuses_non_public_hosts_with_exit_code_2(tmp_path, capsys):
    assert fetchpage.main(["https://localhost/x", "--out-dir", str(tmp_path)]) == 2
    assert "not a public host" in capsys.readouterr().err


def test_a_host_the_network_policy_denies_is_explained(tmp_path, capsys, monkeypatch):
    import urllib.error

    def denied(url, timeout):
        raise urllib.error.URLError("Tunnel connection failed: 403 Forbidden")
    monkeypatch.setattr(fetchpage, "_get", denied)
    assert fetchpage.main(["https://www.linkedin.com/jobs/", "--out-dir", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "does not allow www.linkedin.com" in err and "Allowed domains" in err
    assert not (tmp_path / fetchpage.BLOCKS_FILE).exists()               # not the site's block: nothing recorded
