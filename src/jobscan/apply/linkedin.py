"""LinkedIn Easy Apply, inside `apply run` only (ADR-042).

Deterministic code, not a model: every click, fill and submit is decided here, from the answer bank and the
owner's applicant details. A posting or a page is untrusted text. It is read only for form labels and is shown
to no model, so a posting cannot change a field, a cap or a rule.

Rules:
* a LinkedIn warning or challenge page halts the whole run and starts a cooldown (`start_cooldown`);
* a CAPTCHA, a login wall, a consent or declaration box, a legal, work-authorisation or demographic question,
  or an unknown required field stops this job, and it is handed to the human;
* a submit counts only when the page reports a `/confirmation` address (`ApplyResult` checks it).

The page is reached through the small `Page` protocol, so the rules are tested on fakes. This module has no
LinkedIn selector, no search, no listing crawl, no login and no CAPTCHA solver. A real browser binding is not
built: until it is, `LinkedInEasyApply.apply` hands the job back to the human.
"""

import re
from datetime import UTC, datetime, timedelta
from typing import Protocol

from . import authz
from .adapters import ApplyFailure, ApplyResult, Code, is_confirmation_url, resolve_value
from .consent import FieldClass, classify_field

ADAPTER = authz.LINKEDIN
COOLDOWN_FILE = "state/linkedin-cooldown.json"

_CHALLENGE_PATH = re.compile(r"/(checkpoint|uas|challenge)(/|$|\?)", re.I)
_CHALLENGE_TEXT = re.compile(
    r"unusual activity|security verification|quick security check|account (has been )?restricted"
    r"|temporarily restricted|we noticed (unusual|suspicious)", re.I)
_LOGIN_PATH = re.compile(r"/(login|authwall|signin)(/|$|\?)", re.I)
# Questions no code path answers, whatever the answer bank says (ADR-019, ADR-042).
_OWNER_ONLY = re.compile(
    r"work(ing)? authori[sz]ation|authori[sz]ed to work|right to work|eligib\w* to work|\bvisa\b|sponsor"
    r"|legally|citizen|gender|ethnic|racial|veteran|disabilit|pronoun|salary|compensation|\bpay\b"
    r"|notice period|start date", re.I)


class Page(Protocol):
    def url(self) -> str: ...
    def text(self) -> str: ...
    def has_captcha(self) -> bool: ...
    def fields(self) -> list[dict]: ...          # {"id", "label", "kind", "required", "options"}
    def set_value(self, field_id: str, value: str) -> None: ...
    def attach_file(self, field_id: str, path: str) -> None: ...
    def buttons(self) -> list[str]: ...
    def click(self, name: str) -> None: ...
    def confirmation_url(self) -> str: ...       # "" unless the page reports a confirmation


def _lab(text: str) -> str:
    return " ".join((text or "").split())


def _challenge(page: Page) -> bool:
    return bool(_CHALLENGE_PATH.search(page.url())) or bool(_CHALLENGE_TEXT.search(page.text()))


def _stop_if_blocked(page: Page) -> None:
    """Checked before every step. A challenge halts the run; the other blocks stop this job only."""
    if _challenge(page):
        raise ApplyFailure(Code.LINKEDIN_CHALLENGE, "LinkedIn warning or challenge page", "open")
    if page.has_captcha():
        raise ApplyFailure(Code.CAPTCHA, "captcha present", "open")
    if _LOGIN_PATH.search(page.url()):
        raise ApplyFailure(Code.LOGIN_REQUIRED, "login wall", "open")


def _question(label: str, kind: str, options) -> dict:
    return {"label": label[:200], "kind": kind, "max_length": 0,
            "options": [str(o)[:80] for o in (options or [])][:40]}


def _fill_step(page: Page, applicant: dict, answers: dict, cv_path: str | None):
    filled, consent, unknown, questions = [], [], [], []
    for f in page.fields():
        label = _lab(f.get("label")) or "(unlabelled)"
        kind, required = f.get("kind", "text"), bool(f.get("required"))
        options = f.get("options") or []
        if classify_field(label, kind) is FieldClass.CONSENT_PENDING:
            consent.append(label[:200])
            continue
        if _OWNER_ONLY.search(label):
            unknown.append(label[:200])
            questions.append(_question(label, kind, options))
            continue
        if kind == "file":
            if cv_path:
                page.attach_file(f["id"], cv_path)
                filled.append("resume")
            elif required:
                unknown.append("resume (no CV configured)")
            continue
        value = resolve_value(label, applicant, answers)
        if value is None:
            if required:
                unknown.append(label[:200])
                questions.append(_question(label, kind, options))
            continue
        if options and value.lower() not in {str(o).lower() for o in options}:
            unknown.append(f"{label[:200]} (answer is not one of the options)")
            questions.append(_question(label, kind, options))
            continue
        page.set_value(f["id"], value)
        filled.append(label[:200])
    return filled, consent, unknown, questions


def run_easy_apply(page: Page, applicant: dict, answers: dict, cv_path: str | None, *,
                   submit: bool, max_steps: int = 8) -> ApplyResult:
    """Walk one Easy Apply form. Returns submitted (proof: a /confirmation page), or filled_not_submitted
    when `submit` is false. Anything not certain raises ApplyFailure and the job goes to the human."""
    filled: list[str] = []
    for _ in range(max_steps):
        _stop_if_blocked(page)
        step_filled, consent, unknown, questions = _fill_step(page, applicant, answers, cv_path)
        filled += step_filled
        if consent:
            raise ApplyFailure(Code.CONSENT_PENDING,
                               f"{len(consent)} consent or declaration field(s) need your own answer", "fill",
                               {"consent_fields": consent, "filled_fields": filled})
        if unknown:
            raise ApplyFailure(Code.UNKNOWN_REQUIRED_FIELD,
                               f"{len(unknown)} required field(s) have no pre-approved answer", "fill",
                               {"unknown_fields": unknown, "unknown_questions": questions,
                                "filled_fields": filled})
        buttons = page.buttons()
        if "Submit application" in buttons:
            if not submit:
                return ApplyResult("filled_not_submitted", filled)
            page.click("Submit application")
            confirmation = page.confirmation_url()
            if not is_confirmation_url(confirmation):
                if _challenge(page):
                    raise ApplyFailure(Code.LINKEDIN_CHALLENGE, "challenge page after submit", "submit")
                raise ApplyFailure(Code.SUBMIT_UNCONFIRMED, "clicked submit; no confirmation was shown", "submit")
            return ApplyResult("submitted", filled, confirmation_url=confirmation)
        nxt = next((b for b in buttons if b in ("Review", "Next")), None)
        if nxt is None:
            raise ApplyFailure(Code.FORM_CHANGED, "no Next, Review or Submit button", "fill")
        page.click(nxt)
    raise ApplyFailure(Code.FORM_CHANGED, "more form steps than expected", "fill")


# ----------------------------------------------------------------- cooldown

def cooldown_active(store, now: datetime | None = None) -> bool:
    data = store.read_json(COOLDOWN_FILE, None)
    if not data:
        return False
    return (now or datetime.now(UTC)) < datetime.fromisoformat(data["until"])


def start_cooldown(store, days: int, now: datetime | None = None) -> str:
    start = now or datetime.now(UTC)
    until = (start + timedelta(days=days)).isoformat(timespec="seconds")
    store.write_json(COOLDOWN_FILE, {"until": until, "set_at": start.isoformat(timespec="seconds"),
                                     "reason": "LinkedIn warning or challenge page"})
    return until


# ------------------------------------------------------------------ adapter

class LinkedInEasyApply:
    """The `apply run` entry point. No browser binding is built yet, so no selector is guessed: the job is
    handed to the human as NO_ADAPTER, and nothing is sent."""

    name = ADAPTER

    def apply(self, job, applicant, answers, cv_path, *, submit, headless, hold=False):
        raise ApplyFailure(Code.NO_ADAPTER,
                           "LinkedIn Easy Apply has no verified browser binding yet; apply by hand", "gate")
