"""Answer bank v2: owner-approved answers with provenance, plus the apply-run record.

Lives in career-data as ``answer_bank.yaml`` (ADR-045 keeps identity facts there). Only the owner
writes it. Code fills a form field only from here, and only when the question is not one code
must never answer (sworn attestation, I-9, citizenship, clearance: always NEEDS_ANSWER).

    version: 2
    answers:
      - key: "how_did_you_hear"
        match: ["how did you hear about us", "how did you hear about this job"]
        answer: "LinkedIn"
        scope: standing          # standing | per_job (per_job is never returned as standing)
        source: rui_statement    # rui_statement | cv | rates
        decided_on: 2026-11-04
        quote: "..."             # the owner's words; may be "" for cv and rates sources
        # conflicts:             # optional; with it, answer must be CONFLICT
        #   - {value: "...", source: "..."}
        #   - {value: "...", source: "..."}

``lookup`` searches answer_bank, then profile.yaml ``answers``, then the profile's 01-knowledge
folder, and otherwise returns NEEDS_ANSWER. It is deterministic and makes no network calls.

Work-authorisation answers are returned only when authorization.yaml has
``work_auth_standing.acknowledged_on`` (ADR-044).

``ApplyOutcome`` records one job's result in ``logs/apply/<site>-<date>.jsonl`` in career-data
(ADR-045 hand-off). URLs in every field lose their query string and fragment before writing.

This is separate from ``jobscan.answers`` (apply/answer-bank.yaml, version 1, drafted-answer era).
Neither module logs answer values.
"""

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import yaml

from .applylog import APPLY_STATUSES
from .config import data_root

STANDING = "standing"
PER_JOB = "per_job"
SCOPES = (STANDING, PER_JOB)
SOURCES = ("rui_statement", "cv", "rates")
REQUIRED_KEYS = ("key", "match", "answer", "scope", "source", "decided_on", "quote")
OPTIONAL_KEYS = ("conflicts",)
CONFLICT = "CONFLICT"

ANSWER = "ANSWER"
NEEDS_ANSWER = "NEEDS_ANSWER"

# Always by hand, whatever the bank or profile says (ADR-044).
ALWAYS_HUMAN = re.compile(r"""
    sworn | under\s+oath | under\s+penalty | attest\w* | affirm\w*\s+(?:that|under) |
    \bi[\s-]?9\b | citizen\w* | nationality | clearance
""", re.I | re.X)

# Work-authorisation and sponsorship questions: standing answer only once acknowledged.
WORK_AUTH = re.compile(r"""
    work[\s-]?(?:permit|authori[sz]ation) | authori[sz]ed\s+to\s+work | right\s+to\s+work |
    eligib\w*\s+to\s+work | \bvisa\b | sponsor\w*
""", re.I | re.X)


class AnswerBankError(ValueError):
    pass


class ApplyOutcomeError(ValueError):
    pass


def norm(text: str) -> str:
    """Case, punctuation and spacing removed. The only matching rule: no fuzzy matching."""
    return " ".join(re.sub(r"[^\w\s]", " ", str(text).lower()).split())


@dataclass(frozen=True)
class Conflict:
    value: str
    source: str


@dataclass(frozen=True)
class Entry:
    key: str
    match: tuple
    answer: str
    scope: str
    source: str
    decided_on: date
    quote: str
    conflicts: tuple = ()


@dataclass(frozen=True)
class Result:
    """status is ANSWER, CONFLICT or NEEDS_ANSWER. ``reason`` never contains an answer value."""
    status: str
    value: str | None = None
    options: tuple = ()
    layer: str | None = None
    reason: str = ""


class Bank:
    def __init__(self, entries):
        self.entries = tuple(entries)
        self._by_phrase = {phrase: e for e in self.entries for phrase in e.match}

    def find(self, question: str) -> Entry | None:
        return self._by_phrase.get(norm(question))

    def __len__(self) -> int:
        return len(self.entries)


def _text(value, where: str, *, allow_empty: bool) -> str:
    if not isinstance(value, str):
        raise AnswerBankError(f"{where} must be text")
    if not allow_empty and not value.strip():
        raise AnswerBankError(f"{where} must not be empty")
    return value


def _entry(item, i: int, source_name: str) -> Entry:
    where = f"{source_name}: answers[{i}]"
    if not isinstance(item, dict):
        raise AnswerBankError(f"{where} must be a mapping")
    unknown = set(item) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS)
    if unknown:
        raise AnswerBankError(f"{where} has unknown keys {sorted(unknown)}")
    missing = [k for k in REQUIRED_KEYS if k not in item]
    if missing:
        raise AnswerBankError(f"{where} is missing required keys {missing}")

    key = _text(item["key"], f"{where} key", allow_empty=False)
    where = f"{source_name}: answers[{i}] ({key})"
    if not re.fullmatch(r"[a-z0-9_]+", key):
        raise AnswerBankError(f"{where} key must be lowercase letters, digits and underscores")

    match = item["match"]
    if not isinstance(match, list) or not match:
        raise AnswerBankError(f"{where} match must be a non-empty list of question phrases")
    phrases = []
    for phrase in match:
        text = _text(phrase, f"{where} match entry", allow_empty=False)
        normalised = norm(text)
        if not normalised:
            raise AnswerBankError(f"{where} match entry has no words after normalising")
        if normalised in phrases:
            raise AnswerBankError(f"{where} repeats a match phrase")
        phrases.append(normalised)

    answer = _text(item["answer"], f"{where} answer", allow_empty=True)

    scope = item["scope"]
    if scope not in SCOPES:
        raise AnswerBankError(f"{where} scope must be one of {', '.join(SCOPES)}")
    source = item["source"]
    if source not in SOURCES:
        raise AnswerBankError(f"{where} source must be one of {', '.join(SOURCES)}")

    decided = item["decided_on"]
    if isinstance(decided, str):
        try:
            decided = date.fromisoformat(decided)
        except ValueError:
            raise AnswerBankError(f"{where} decided_on must be an ISO date")
    if not isinstance(decided, date):
        raise AnswerBankError(f"{where} decided_on must be an ISO date")

    quote = _text(item["quote"], f"{where} quote", allow_empty=True)

    conflicts: tuple = ()
    if "conflicts" in item:
        raw = item["conflicts"]
        if not isinstance(raw, list) or len(raw) < 2:
            raise AnswerBankError(f"{where} conflicts must list at least two options")
        options = []
        for n, opt in enumerate(raw, start=1):
            if not isinstance(opt, dict) or set(opt) != {"value", "source"}:
                raise AnswerBankError(f"{where} conflicts[{n}] must have exactly value and source")
            options.append(Conflict(
                value=_text(opt["value"], f"{where} conflicts[{n}] value", allow_empty=False),
                source=_text(opt["source"], f"{where} conflicts[{n}] source", allow_empty=False),
            ))
        if answer != CONFLICT:
            raise AnswerBankError(f"{where} has conflicts, so answer must be {CONFLICT}")
        conflicts = tuple(options)
    elif answer == CONFLICT:
        raise AnswerBankError(f"{where} answer is {CONFLICT} but no conflicts are listed")

    return Entry(key=key, match=tuple(phrases), answer=answer, scope=scope, source=source,
                 decided_on=decided, quote=quote, conflicts=conflicts)


def load(path) -> Bank:
    """Read and validate answer_bank.yaml. Errors name the entry key, never an answer value."""
    p = Path(path)
    if not p.is_file():
        raise AnswerBankError(f"{p}: not found")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AnswerBankError(f"{p}: not valid YAML ({exc})")
    if not isinstance(data, dict):
        raise AnswerBankError(f"{p}: top level must be a mapping with version and answers")
    if data.get("version") != 2:
        raise AnswerBankError(f"{p}: version must be 2")
    raw = data.get("answers")
    if not isinstance(raw, list):
        raise AnswerBankError(f"{p}: answers must be a list (use [] for none)")

    entries, keys, phrases = [], set(), set()
    name = p.name
    for i, item in enumerate(raw, start=1):
        entry = _entry(item, i, name)
        if entry.key in keys:
            raise AnswerBankError(f"{name}: duplicate key {entry.key!r}")
        keys.add(entry.key)
        for phrase in entry.match:
            if phrase in phrases:
                raise AnswerBankError(f"{name}: match phrase used by two entries (key {entry.key!r})")
            phrases.add(phrase)
        entries.append(entry)
    return Bank(entries)


def load_knowledge(folder) -> dict:
    """Exact question headings in a 01-knowledge folder: ``## <question>`` then its first paragraph."""
    base = Path(folder)
    found: dict = {}
    if not base.is_dir():
        return found
    for path in sorted(base.glob("*.md")):
        heading = None
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                heading = norm(line[3:]) if line.startswith("## ") else None
                if heading:
                    found.setdefault(heading, None)
                continue
            if heading and line.strip() and found.get(heading) is None:
                found[heading] = line.strip()
    return {k: v for k, v in found.items() if v}


def work_auth_acknowledged(authorization) -> bool:
    block = (authorization or {}).get("work_auth_standing") or {}
    ack = block.get("acknowledged_on")
    if isinstance(ack, date):
        return True
    if isinstance(ack, str):
        try:
            date.fromisoformat(ack)
            return True
        except ValueError:
            return False
    return False


def _guard(question: str, match_text: str, authorization) -> Result | None:
    """Return a refusal when policy forbids a standing answer, otherwise None."""
    if ALWAYS_HUMAN.search(question) or ALWAYS_HUMAN.search(match_text):
        return Result(NEEDS_ANSWER, reason="always answered by hand (attestation, identity or clearance)")
    if (WORK_AUTH.search(question) or WORK_AUTH.search(match_text)) and not work_auth_acknowledged(authorization):
        return Result(NEEDS_ANSWER, reason="work authorisation not acknowledged in authorization.yaml")
    return None


def lookup(question: str, *, bank: Bank, profile: dict | None = None, knowledge: dict | None = None,
           authorization: dict | None = None) -> Result:
    """Find an approved standing answer. Order: answer_bank, profile answers, 01-knowledge, else NEEDS_ANSWER."""
    refusal = _guard(question, "", authorization)
    if refusal:
        return refusal

    entry = bank.find(question)
    if entry is not None:
        refusal = _guard(question, " ".join(entry.match), authorization)
        if refusal:
            return refusal
        if entry.scope == PER_JOB:
            return Result(NEEDS_ANSWER, layer="answer_bank", reason="per-job entry, not a standing answer")
        if entry.conflicts:
            return Result(CONFLICT, options=tuple((c.value, c.source) for c in entry.conflicts),
                          layer="answer_bank", reason="sources disagree; owner must decide")
        if not entry.answer.strip():
            return Result(NEEDS_ANSWER, layer="answer_bank", reason="unknown in answer bank")
        return Result(ANSWER, value=entry.answer, layer="answer_bank")

    answers = (profile or {}).get("answers") or {}
    if not isinstance(answers, dict):
        answers = {}
    wanted = norm(question)
    for raw_key, raw_value in answers.items():
        if norm(raw_key) == wanted and raw_value is not None and str(raw_value).strip():
            refusal = _guard(question, str(raw_key), authorization)
            if refusal:
                return refusal
            return Result(ANSWER, value=str(raw_value), layer="profile")

    if knowledge and wanted in knowledge:
        refusal = _guard(question, "", authorization)
        if refusal:
            return refusal
        return Result(ANSWER, value=knowledge[wanted], layer="knowledge")

    return Result(NEEDS_ANSWER, reason="no approved answer in bank, profile or knowledge")


# ---- apply-run record (ADR-045) -------------------------------------------------------------

STATUSES = APPLY_STATUSES
VERIFIED_BY = ("confirmation_url", "gmail", "human", "site_applied_list")
_URL = re.compile(r"https?://[^\s\"'<>]+")
_SITE = re.compile(r"[a-z0-9][a-z0-9-]*")


@dataclass(frozen=True)
class ApplyOutcome:
    job_id: str
    employer: str
    role: str
    site: str
    status: str
    verified_by: str
    ts: str


def redact(text: str) -> str:
    """Drop the query string and fragment from every URL in the text."""
    def strip(m):
        parts = urlsplit(m.group(0))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return _URL.sub(strip, str(text))


def validate_outcome(o: ApplyOutcome) -> ApplyOutcome:
    for field in ("job_id", "site", "status", "ts"):
        if not str(getattr(o, field)).strip():
            raise ApplyOutcomeError(f"{field} is required")
    if o.status not in STATUSES:
        raise ApplyOutcomeError(f"status must be one of {', '.join(STATUSES)}")
    if o.verified_by and o.verified_by not in VERIFIED_BY:
        raise ApplyOutcomeError(f"verified_by must be one of {', '.join(VERIFIED_BY)}")
    if o.status == "SUBMITTED" and not o.verified_by:
        raise ApplyOutcomeError("a SUBMITTED outcome must say how it was verified")
    if o.status == "ALREADY_APPLIED" and o.verified_by not in ("site_applied_list", "human"):
        raise ApplyOutcomeError("an ALREADY_APPLIED outcome must be verified by site_applied_list or human")
    if not _SITE.fullmatch(o.site):
        raise ApplyOutcomeError("site must be a lowercase slug such as greenhouse")
    try:
        datetime.fromisoformat(o.ts)
    except ValueError:
        raise ApplyOutcomeError("ts must be an ISO date or datetime")
    return o


def outcome_path(root: Path, site: str, ts: str) -> Path:
    stamp = ts[:10]
    date.fromisoformat(stamp)
    return root / "logs" / "apply" / f"{site}-{stamp}.jsonl"


def append_outcome(outcome: ApplyOutcome, data: str | None = None) -> Path:
    """Append one redacted line to logs/apply/<site>-<date>.jsonl in career-data."""
    o = validate_outcome(outcome)
    clean = ApplyOutcome(**{k: redact(v) for k, v in asdict(o).items()})
    path = outcome_path(data_root(data), clean.site, clean.ts)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(clean), sort_keys=True, ensure_ascii=False) + "\n")
    return path
