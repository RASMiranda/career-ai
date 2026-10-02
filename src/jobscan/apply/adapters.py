"""Form adapters for ATS-hosted application pages (Greenhouse, Lever, Ashby...).

No LinkedIn Easy Apply, no logins, no CAPTCHA handling, no LLM in the loop.
Anything the code is not certain about ends in an ApplyFailure, which the
runner turns into "apply manually" plus a redacted log entry.

STATUS: tested against a local fixture form only. Real ATS pages differ; use
`run --dry-run` first and feed the failure bundle back to Claude Code to tune.
"""

import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse


class Code:
    NO_ADAPTER = "NO_ADAPTER"
    CAPTCHA = "CAPTCHA"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    UNKNOWN_REQUIRED_FIELD = "UNKNOWN_REQUIRED_FIELD"
    CV_MISSING = "CV_MISSING"
    UPLOAD_FAILED = "UPLOAD_FAILED"
    FORM_CHANGED = "FORM_CHANGED"
    JOB_CLOSED = "JOB_CLOSED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    TIMEOUT = "TIMEOUT"
    NETWORK = "NETWORK"
    SUBMIT_UNCONFIRMED = "SUBMIT_UNCONFIRMED"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"
    INTERNAL = "INTERNAL"


class ApplyFailure(Exception):
    def __init__(self, code: str, message: str, step: str = "", details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.step = code, message, step
        self.details = details or {}


@dataclass
class ApplyResult:
    status: str                      # submitted | filled_not_submitted
    filled: list[str] = field(default_factory=list)
    confirmation: str = ""


ATS_HOSTS = {
    "greenhouse": ("boards.greenhouse.io", "job-boards.greenhouse.io"),
    "lever": ("jobs.lever.co",),
    "ashby": ("jobs.ashbyhq.com",),
    "workable": ("apply.workable.com",),
}


def detect_ats(url: str) -> str | None:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return None
    for name, hosts in ATS_HOSTS.items():
        if any(host == h or host.endswith("." + h) for h in hosts):
            return name
    return None


# --------------------------------------------------------------------- answers

_BUILTIN = [  # (regex on normalised label, applicant key); first match wins
    (r"first name|given name", "first_name"),
    (r"last name|surname|family name", "last_name"),
    (r"full name|^name$|your name", "full_name"),
    (r"e ?mail", "email"),
    (r"phone|mobile|telephone", "phone"),
    (r"linkedin", "linkedin"),
    (r"github", "github"),
    (r"website|portfolio|personal site", "website"),
    (r"current location|city|location", "location"),
    (r"current company|current employer|company name", "current_company"),
]


def _lab(text: str) -> str:
    text = re.sub(r"[*✱:()?]", " ", (text or "").lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]", " ", text)).strip()


def resolve_value(label: str, applicant: dict, answers: dict) -> str | None:
    """Explicit answers win over built-ins. Empty or missing means 'unknown'."""
    lab = _lab(label)
    if not lab:
        return None
    for needle, val in (answers or {}).items():
        if val not in (None, "") and _lab(needle) in lab:
            return str(val)
    data = {**applicant}
    if not data.get("full_name"):
        data["full_name"] = f"{data.get('first_name','')} {data.get('last_name','')}".strip()
    for pattern, key in _BUILTIN:
        if re.search(pattern, lab):
            return str(data[key]) if data.get(key) else None
    return None


# ------------------------------------------------------------------ page logic

_JS_LABEL = """e => {
  const t = n => ((n && n.innerText) || '').trim();
  if (e.getAttribute('aria-label')) return e.getAttribute('aria-label');
  if (e.id) { const l = document.querySelector('label[for="' + CSS.escape(e.id) + '"]'); if (l) return t(l); }
  const p = e.closest('label'); if (p) return t(p);
  const lb = e.getAttribute('aria-labelledby');
  if (lb) { const n = document.getElementById(lb.split(' ')[0]); if (n) return t(n); }
  const w = e.closest('[class*="field"],[class*="question"],fieldset,div');
  const l2 = w && w.querySelector('label, legend');
  return l2 ? t(l2) : (e.placeholder || e.name || '');
}"""

_JS_GROUP = """e => {
  const fs = e.closest('fieldset');
  if (fs) { const l = fs.querySelector('legend'); if (l) return l.innerText.trim(); }
  const w = e.closest('[class*="question"],[class*="field"]') || e.parentElement;
  const l2 = w && w.querySelector('legend, .group-label, [class*="label"]');
  return l2 ? l2.innerText.trim() : '';
}"""

_JS_REQUIRED = """e => e.required || e.getAttribute('aria-required') === 'true'"""

_JS_CAPTCHA = """() => {
  const sel = 'iframe[src*="hcaptcha"], iframe[src*="recaptcha"], .g-recaptcha, .h-captcha, '
            + '[data-sitekey], iframe[src*="turnstile"], .cf-turnstile';
  return [...document.querySelectorAll(sel)].some(n => {
    if (n.closest('.grecaptcha-badge')) return false;     // invisible v3 badge
    const r = n.getBoundingClientRect(), s = getComputedStyle(n);
    return r.width > 50 && r.height > 30 && s.visibility !== 'hidden' && s.display !== 'none';
  });
}"""

_CLOSED = re.compile(
    r"no longer (accepting|available)|position (has been )?filled|"
    r"(job|posting|position) (not found|is closed|has expired|has been removed)|page not found",
    re.I)
_SUCCESS = re.compile(
    r"thank you|application (has been )?(submitted|received|sent)|"
    r"we.ve received|successfully submitted", re.I)
_LOGIN = re.compile(r"\b(sign in|log in|create an account)\b", re.I)

_TEXT_CONTROLS = (
    "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=file])"
    ":not([type=checkbox]):not([type=radio]), textarea, select"
)


class Adapter:
    name = "base"

    def apply(self, job: dict, applicant: dict, answers: dict, cv_path: str | None, *,
              submit: bool, headless: bool, hold: bool = False) -> ApplyResult:
        raise NotImplementedError


class FormAdapter(Adapter):
    def __init__(self, ats: str):
        self.name = ats

    # -- public ---------------------------------------------------------------
    def apply(self, job, applicant, answers, cv_path, *, submit, headless, hold=False):
        from playwright.sync_api import TimeoutError as PWTimeout
        from playwright.sync_api import sync_playwright

        step = "open"
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            page = browser.new_context().new_page()
            try:
                resp = page.goto(job["url"], timeout=30_000, wait_until="domcontentloaded")
                if resp is not None and resp.status in (404, 410):
                    raise ApplyFailure(Code.JOB_CLOSED, f"HTTP {resp.status}", step)
                if resp is not None and resp.status >= 400:
                    raise ApplyFailure(Code.NETWORK, f"HTTP {resp.status}", step)
                self._raise_if_closed(page, step)

                step = "reach_form"
                self._reach_form(page)
                self._raise_if_captcha(page, "pre_fill")

                step = "fill"
                filled = self._fill(page, applicant, answers, cv_path)
                self._raise_if_captcha(page, "post_fill")

                if not submit:
                    if hold and not headless:
                        input("Form is filled. Review it, submit it yourself, "
                              "then press Enter here to close the browser... ")
                    return ApplyResult("filled_not_submitted", filled)

                step = "submit"
                return ApplyResult("submitted", filled, self._submit(page))
            except ApplyFailure as fail:
                fail.step = fail.step or step
                fail.details.setdefault("form_outline", self._outline(page))
                raise
            except PWTimeout as exc:
                raise ApplyFailure(Code.TIMEOUT, type(exc).__name__, step,
                                   {"form_outline": self._outline(page)}) from exc
            finally:
                browser.close()

    # -- steps ----------------------------------------------------------------
    def _raise_if_closed(self, page, step):
        if _CLOSED.search(self._body(page)):
            raise ApplyFailure(Code.JOB_CLOSED, "closed-posting text on page", step)

    def _reach_form(self, page):
        def has_form():
            return len([e for e in page.query_selector_all(_TEXT_CONTROLS) if e.is_visible()]) >= 2
        if has_form():
            return
        link = page.get_by_role("link", name=re.compile(r"\bapply\b", re.I)).first
        btn = page.get_by_role("button", name=re.compile(r"\bapply\b", re.I)).first
        for target in (link, btn):
            if target.count():
                target.click()
                page.wait_for_load_state("domcontentloaded")
                break
        if not has_form():
            code = Code.LOGIN_REQUIRED if _LOGIN.search(self._body(page)) else Code.FORM_CHANGED
            raise ApplyFailure(code, "no application form found", "reach_form")

    def _raise_if_captcha(self, page, step):
        if page.evaluate(_JS_CAPTCHA):
            raise ApplyFailure(Code.CAPTCHA, "captcha widget present", step)

    def _fill(self, page, applicant, answers, cv_path) -> list[str]:
        filled, unknown = [], []

        for el in page.query_selector_all(_TEXT_CONTROLS):
            if not el.is_visible() or el.is_disabled():
                continue
            label, required = el.evaluate(_JS_LABEL), el.evaluate(_JS_REQUIRED)
            value = resolve_value(label, applicant, answers)
            if value is None:
                if required:
                    unknown.append(label.strip(" *✱"))
                continue
            try:
                if el.evaluate("e => e.tagName.toLowerCase()") == "select":
                    try:
                        el.select_option(label=value)
                    except Exception:
                        el.select_option(value=value)
                else:
                    el.fill(value)
                filled.append(label.strip(" *✱"))
            except Exception:
                unknown.append(f"{label.strip(' *✱')} (could not set answer)")

        # checkboxes: only ticked when you pre-approved an explicit yes
        for el in page.query_selector_all("input[type=checkbox]"):
            if not el.evaluate(_JS_REQUIRED) or el.is_disabled():
                continue
            label = el.evaluate(_JS_LABEL)
            value = resolve_value(label, applicant, answers)
            if value and value.strip().lower() in ("yes", "true", "1", "agree"):
                el.check()
                filled.append(label.strip(" *✱"))
            else:
                unknown.append(label.strip(" *✱"))

        # radios: required groups need a pre-approved answer that matches an option
        groups: dict[str, list] = {}
        for el in page.query_selector_all("input[type=radio]"):
            groups.setdefault(el.get_attribute("name") or el.get_attribute("id") or "?", []).append(el)
        for els in groups.values():
            if not any(e.evaluate(_JS_REQUIRED) for e in els):
                continue
            question = els[0].evaluate(_JS_GROUP)
            value = resolve_value(question, applicant, answers)
            chosen = next((e for e in els
                           if value and _lab(e.evaluate(_JS_LABEL)) == _lab(value)), None)
            if chosen is None:
                unknown.append(question.strip(" *✱") or "(unlabelled choice)")
            else:
                chosen.check()
                filled.append(question.strip(" *✱"))

        # CV
        files = page.query_selector_all("input[type=file]")
        if files and cv_path:
            try:
                files[0].set_input_files(cv_path)
                filled.append("resume")
            except Exception as exc:
                raise ApplyFailure(Code.UPLOAD_FAILED, type(exc).__name__, "fill") from exc
        elif files and files[0].evaluate(_JS_REQUIRED):
            unknown.append("resume (no CV configured)")

        if unknown:
            raise ApplyFailure(
                Code.UNKNOWN_REQUIRED_FIELD,
                f"{len(unknown)} required field(s) have no pre-approved answer", "fill",
                {"unknown_fields": unknown, "filled_fields": filled})
        return filled

    def _submit(self, page) -> str:
        btn = page.get_by_role("button", name=re.compile(r"^(submit|send|apply)\b", re.I))
        if not btn.count():
            raise ApplyFailure(Code.FORM_CHANGED, "no submit button", "submit")
        btn.first.click()
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                body = self._body(page)
            except Exception:           # navigation in flight
                time.sleep(0.5)
                continue
            m = _SUCCESS.search(body)
            if m:
                return m.group(0)
            time.sleep(0.5)

        errors = page.evaluate(
            "() => [...document.querySelectorAll('[aria-invalid=true], .error, [class*=error]')]"
            ".map(n => (n.innerText || n.name || '').trim()).filter(Boolean).slice(0, 10)")
        if errors:
            raise ApplyFailure(Code.VALIDATION_ERROR, "site reported validation errors",
                               "submit", {"visible_errors": errors})
        if page.evaluate(_JS_CAPTCHA):
            raise ApplyFailure(Code.CAPTCHA, "captcha appeared after submit", "submit")
        raise ApplyFailure(Code.SUBMIT_UNCONFIRMED, "clicked submit; no confirmation seen", "submit")

    # -- helpers --------------------------------------------------------------
    @staticmethod
    def _body(page) -> str:
        return page.inner_text("body", timeout=5000)

    @staticmethod
    def _outline(page) -> dict:
        """Describe the form WITHOUT values, so a failure can be reproduced
        from a fixture without leaking anything personal."""
        try:
            controls = page.evaluate("""() => [...document.querySelectorAll(
                'input:not([type=hidden]), textarea, select')].slice(0, 60).map(e => ({
                  tag: e.tagName.toLowerCase(), type: e.type || '', name: e.name || '',
                  required: !!(e.required || e.getAttribute('aria-required') === 'true'),
                  label: ((e.labels && e.labels[0] && e.labels[0].innerText) ||
                          e.getAttribute('aria-label') || e.placeholder || '').trim().slice(0, 120)
                }))""")
            parsed = urlparse(page.url)
            return {"controls": controls, "page_title": page.title()[:120],
                    "final_url": f"{parsed.hostname}{parsed.path}"}
        except Exception:
            return {"controls": [], "note": "outline unavailable"}


def pick_adapter(url: str, allowed: list[str] | None = None) -> Adapter | None:
    ats = detect_ats(url)
    if ats is None or (allowed is not None and ats not in allowed):
        return None
    return FormAdapter(ats)
