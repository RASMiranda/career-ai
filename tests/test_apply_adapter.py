"""Drives the real Playwright adapter against a local fake application site.

The fake server counts POSTs, so 'nothing was submitted' is proven, not assumed.
Skipped automatically if Chromium is not available.
"""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytest.importorskip("playwright")

from jobscan.apply.adapters import ApplyFailure, Code, FormAdapter  # noqa: E402

BASE = """<html><head><title>Apply</title></head><body><h1>Senior Engineer</h1>
<form method="POST" action="/submit">
<div class="field"><label for="fn">First name *</label><input id="fn" name="fn" required></div>
<div class="field"><label for="ln">Last name *</label><input id="ln" name="ln" required></div>
<div class="field"><label for="em">Email *</label><input id="em" name="em" type="email" required></div>
<div class="field"><label for="ph">Phone</label><input id="ph" name="ph"></div>
<div class="field"><label for="li">LinkedIn Profile</label><input id="li" name="li"></div>
<div class="field"><label for="cv">Resume *</label><input id="cv" type="file" name="cv" required></div>
{extra}
<button type="submit">Submit application</button></form></body></html>"""

PAGES = {
    "/ok": BASE.format(extra=""),
    "/salary": BASE.format(extra='<div class="field"><label for="s">Salary expectations *</label>'
                                 '<textarea id="s" name="s" required></textarea></div>'),
    "/radio": BASE.format(extra='<fieldset class="field"><legend>Are you authorized to work in the EU? *'
                                '</legend><label><input type="radio" name="a" value="y" required> Yes</label>'
                                '<label><input type="radio" name="a" value="n" required> No</label></fieldset>'),
    "/consent": BASE.format(extra='<label><input type="checkbox" name="c" required> '
                                  'I agree to the privacy policy *</label>'),
    "/captcha": BASE.format(extra='<div class="g-recaptcha" style="width:300px;height:80px"></div>'),
    "/questions": BASE.format(extra=(
        '<div class="field"><label for="yj">Years of Java experience *</label><select id="yj" name="yj" required>'
        '<option value="">Select...</option><option>0-2</option><option>3-5</option><option>6+</option></select></div>'
        '<div class="field"><label for="why">Why do you want to work here? *</label>'
        '<textarea id="why" name="why" maxlength="600" required></textarea></div>'
        '<div class="field"><label for="sb">How many years of Spring Boot? *</label>'
        '<input id="sb" name="sb" type="number" required></div>'
        '<fieldset class="field"><legend>Are you comfortable with on-call rotation? *</legend>'
        '<label><input type="radio" name="oc" value="y" required> Yes</label>'
        '<label><input type="radio" name="oc" value="n" required> No</label></fieldset>'
        '<label><input type="checkbox" name="c" required> I agree to the privacy policy *</label>')),
    "/closed": "<html><body><h1>Sorry, this position is no longer accepting applications.</h1></body></html>",
}
APPLICANT = {"first_name": "Ana", "last_name": "Silva", "email": "ana@example.test", "phone": ""}


@pytest.fixture(scope="module")
def site():
    posts = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, body, code=200):
            self.send_response(code); self.send_header("Content-Type", "text/html")
            self.end_headers(); self.wfile.write(body.encode())
        def do_GET(self):
            self._send(PAGES.get(self.path, "<h1>Page not found</h1>"), 200 if self.path in PAGES else 404)
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            posts.append(self.path)
            self._send("<h1>Thank you for applying</h1>")

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", posts
    srv.shutdown()


@pytest.fixture
def cv(tmp_path):
    f = tmp_path / "cv.pdf"; f.write_bytes(b"%PDF-1.4 test")
    return str(f)


@pytest.fixture(autouse=True)
def _browser_available():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
    except Exception as exc:
        pytest.skip(f"chromium unavailable: {type(exc).__name__}")


def run(site, path, answers=None, cv=None, submit=False):
    base, posts = site
    before = len(posts)
    try:
        res = FormAdapter("greenhouse").apply({"url": base + path}, APPLICANT, answers or {}, cv,
                                              submit=submit, headless=True)
        return res, None, len(posts) - before
    except ApplyFailure as f:
        return None, f, len(posts) - before


def test_dry_run_fills_but_never_submits(site, cv):
    res, fail, posted = run(site, "/ok", cv=cv, submit=False)
    assert fail is None and res.status == "filled_not_submitted" and posted == 0
    assert {"First name", "Last name", "Email", "resume"} <= set(res.filled)
    assert "Phone" not in res.filled           # empty applicant value is not invented


def test_submit_posts_once_and_confirms(site, cv):
    res, fail, posted = run(site, "/ok", cv=cv, submit=True)
    assert fail is None and res.status == "submitted" and posted == 1
    assert "thank you" in res.confirmation.lower()


def test_unknown_required_question_stops_before_submit(site, cv):
    res, fail, posted = run(site, "/salary", cv=cv, submit=True)
    assert fail.code == Code.UNKNOWN_REQUIRED_FIELD and posted == 0
    assert fail.details["unknown_fields"] == ["Salary expectations"]
    assert any(c["label"].startswith("Salary") for c in fail.details["form_outline"]["controls"])


def test_preapproved_answer_unblocks_it(site, cv):
    res, fail, posted = run(site, "/salary", {"salary expectation": "Negotiable"}, cv=cv, submit=True)
    assert fail is None and posted == 1 and "Salary expectations" in res.filled


def test_work_authorisation_radio_needs_explicit_answer(site, cv):
    _, fail, posted = run(site, "/radio", cv=cv, submit=True)
    assert fail.code == Code.UNKNOWN_REQUIRED_FIELD and posted == 0
    assert "authorized to work" in fail.details["unknown_fields"][0].lower()
    res, fail, posted = run(site, "/radio", {"authorized to work": "Yes"}, cv=cv, submit=True)
    assert fail is None and posted == 1


def test_consent_box_is_never_ticked_unless_you_said_so(site, cv):
    _, fail, posted = run(site, "/consent", cv=cv, submit=True)
    assert fail.code == Code.UNKNOWN_REQUIRED_FIELD and posted == 0
    res, fail, posted = run(site, "/consent", {"privacy policy": "yes"}, cv=cv, submit=True)
    assert fail is None and posted == 1


def test_captcha_is_never_attempted(site, cv):
    _, fail, posted = run(site, "/captcha", cv=cv, submit=True)
    assert fail.code == Code.CAPTCHA and posted == 0


def test_closed_posting_detected(site, cv):
    _, fail, posted = run(site, "/closed", cv=cv, submit=True)
    assert fail.code == Code.JOB_CLOSED and posted == 0


def test_http_404_is_job_closed(site, cv):
    _, fail, posted = run(site, "/gone", cv=cv)
    assert fail.code == Code.JOB_CLOSED and posted == 0


def test_missing_required_cv_stops(site):
    _, fail, posted = run(site, "/ok", cv=None, submit=True)
    assert fail.code == Code.UNKNOWN_REQUIRED_FIELD and "resume" in fail.details["unknown_fields"][0]
    assert posted == 0


def test_unknown_questions_carry_their_shape_so_an_answer_can_be_drafted(site, cv):
    _, fail, posted = run(site, "/questions", cv=cv, submit=True)
    assert fail.code == Code.UNKNOWN_REQUIRED_FIELD and posted == 0
    got = {q["label"]: q for q in fail.details["unknown_questions"]}
    assert set(got) == set(fail.details["unknown_fields"])                    # same questions, richer
    assert got["Years of Java experience"]["kind"] == "select"
    assert got["Years of Java experience"]["options"] == ["0-2", "3-5", "6+"]  # placeholder dropped
    assert got["Why do you want to work here?"] == {
        "label": "Why do you want to work here?", "kind": "textarea", "max_length": 600, "options": []}
    assert got["How many years of Spring Boot?"]["kind"] == "number"
    assert got["Are you comfortable with on-call rotation?"]["kind"] == "radio"
    assert got["Are you comfortable with on-call rotation?"]["options"] == ["Yes", "No"]
    assert got["I agree to the privacy policy"]["kind"] == "checkbox"


def test_answers_in_the_drafted_shape_fill_the_form(site, cv):
    answers = {"years of java experience": "6+", "why do you want": "I like platform work.",
               "years of spring boot": "7", "on-call rotation": "Yes", "privacy policy": "yes"}
    res, fail, posted = run(site, "/questions", answers, cv=cv, submit=True)
    assert fail is None and posted == 1
    assert {"Years of Java experience", "Why do you want to work here?"} <= set(res.filled)
