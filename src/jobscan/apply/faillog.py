"""Structured, redacted failure log + a shareable repro bundle."""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from .. import __version__

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<![\w])\+?\d[\d\s().-]{7,}\d(?![\w])")

EXPLAIN = {
    "NO_ADAPTER": "No automatic adapter exists for this site.",
    "CAPTCHA": "The site asked for a CAPTCHA. This tool never solves those.",
    "LOGIN_REQUIRED": "The site wants an account or login first.",
    "UNKNOWN_REQUIRED_FIELD": "The form asks required questions with no pre-approved answer.",
    "CV_MISSING": "The CV file configured for this role was not found.",
    "UPLOAD_FAILED": "The CV upload did not work.",
    "FORM_CHANGED": "The page layout did not match what the adapter expects.",
    "JOB_CLOSED": "The posting looks closed or removed.",
    "VALIDATION_ERROR": "The site rejected the form with validation errors.",
    "TIMEOUT": "The page timed out.",
    "NETWORK": "A network error occurred.",
    "SUBMIT_UNCONFIRMED": "Submit was clicked but no confirmation appeared. It may or may not have gone through — check before retrying.",
    "BLOCKED_BY_POLICY": "Skipped by your own safety rules.",
    "INTERNAL": "Unexpected error in the tool itself.",
}


def redact(value, secrets=()):
    if isinstance(value, dict):
        return {k: redact(v, secrets) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v, secrets) for v in value]
    if not isinstance(value, str):
        return value
    # Patterns first: replacing a name inside an address would leave the
    # rest of the address behind and defeat the email pattern.
    value = _EMAIL.sub("[email]", value)
    value = _PHONE.sub("[phone]", value)
    for s in secrets:
        if s and len(s) >= 3:
            value = re.sub(re.escape(s), "[REDACTED]", value, flags=re.I)
    return value[:400]


def host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


class FailureLog:
    def __init__(self, root: Path, secrets=()):
        self.dir = root / "logs" / "apply"
        self.secrets = [s for s in secrets if s]

    def write(self, entry: dict) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        entry = redact({
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tool_version": __version__,
            **entry,
        }, self.secrets)
        path = self.dir / f"{entry['at'][:10]}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return path

    def read_since(self, days: int) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        out = []
        for path in sorted(self.dir.glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if datetime.fromisoformat(row["at"]) >= cutoff:
                    out.append(row)
        return out


BUNDLE_HEADER = """\
# Apply-adapter failure bundle

You are helping improve `career-ai`, a job-application tool. Below are
sanitised failures from its form-filling adapters (`src/jobscan/apply/adapters.py`).
No names, emails, phone numbers, companies or job titles are included.

For each failure group:
1. Say which error code and step it is and what the likely cause is.
2. Propose the smallest change to the adapter (selector, label mapping, wait,
   or a new error code), or say the right outcome is "hand to human".
3. Write a pytest case that reproduces it against a local HTML fixture
   built from the `form_outline`.

Hard constraints: never solve or bypass CAPTCHAs, never auto-answer legal
consent or work-authorisation questions, never invent applicant data.

"""


def bundle(entries: list[dict]) -> str:
    groups: dict[tuple, list] = {}
    for e in entries:
        groups.setdefault((e.get("ats", "?"), e.get("error_code"), e.get("step")), []).append(e)
    lines = [BUNDLE_HEADER, f"{len(entries)} failure(s) in {len(groups)} group(s).\n"]
    for (ats, code, step), rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"## {ats} · {code} · step `{step}` · x{len(rows)}\n")
        for r in rows[:3]:
            safe = {
                "host": host_of(r.get("url", "")),
                "adapter": r.get("adapter"), "mode": r.get("mode"),
                "message": r.get("message"), "details": r.get("details", {}),
                "tool_version": r.get("tool_version"),
            }
            lines += ["```json", json.dumps(safe, indent=2, ensure_ascii=False), "```", ""]
    return "\n".join(lines)
