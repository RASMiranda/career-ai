"""Answer bank: owner-written answers to exact application questions.

Lives in career-data as ``apply/answer-bank.yaml``:

    version: 1
    answers:
      - question: "Are you a family member or relative of anyone at this company?"
        answer: "No"            # always quote: YAML reads a bare No as false, a bare 15 as a number
        per_job: false          # false = the same answer for every job (standing)
        note: "Owner, 2026-11-04"

``find(question)`` returns the answer, or None, and None means the human is asked. Never guess.
Matching is exact after case, spacing and punctuation are removed; there is no fuzzy matching.
Work-authorisation, background-check and criminal-record questions return None unless the exact
entry is flagged ``per_job: false``. An empty answer means unknown.

This is separate from ``jobscan.apply.answers`` (drafted, model-written answers, ADR-019).
"""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


class AnswerBankError(ValueError):
    pass


REFUSED = re.compile(r"""
    work[\s-]?(?:permit|authori[sz]ation)|authori[sz]ed\s+to\s+work|right\s+to\s+work|eligib\w*\s+to\s+work|
    \bvisa\b|sponsor\w*|
    background\s+(?:check|screen\w*)|criminal|convict\w*|felony|police\s+record
""", re.I | re.X)


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", str(text).lower()).split())


@dataclass(frozen=True)
class Entry:
    question: str
    answer: str
    per_job: bool


class Bank:
    def __init__(self, entries):
        self.entries = list(entries)
        self._by_question = {_norm(e.question): e for e in self.entries}

    def find(self, question_text: str) -> str | None:
        entry = self._by_question.get(_norm(question_text))
        if entry is None or not entry.answer.strip():
            return None
        if entry.per_job and REFUSED.search(question_text):
            return None
        return entry.answer

    def __len__(self) -> int:
        return len(self.entries)


def load(path) -> Bank:
    """Read and validate the bank. Any missing or malformed key raises AnswerBankError."""
    p = Path(path)
    if not p.is_file():
        raise AnswerBankError(f"{p}: not found")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AnswerBankError(f"{p}: not valid YAML ({exc})")
    if not isinstance(data, dict):
        raise AnswerBankError(f"{p}: top level must be a mapping with version and answers")
    if data.get("version") != 1:
        raise AnswerBankError(f"{p}: version must be 1")
    raw = data.get("answers")
    if not isinstance(raw, list):
        raise AnswerBankError(f"{p}: answers must be a list (use [] for none)")
    entries, seen = [], set()
    for i, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise AnswerBankError(f"{p}: answers[{i}] must be a mapping")
        for key in ("question", "answer"):
            if key not in item:
                raise AnswerBankError(f"{p}: answers[{i}] is missing required key {key!r}")
        question, answer = item["question"], item["answer"]
        if not isinstance(question, str) or not question.strip():
            raise AnswerBankError(f"{p}: answers[{i}] question must be non-empty text")
        if not isinstance(answer, str):
            raise AnswerBankError(f"{p}: answers[{i}] answer must be quoted text, "
                                  f"use \"\" for unknown (a bare No or 15 is read as a boolean or number)")
        per_job = item.get("per_job", True)
        if not isinstance(per_job, bool):
            raise AnswerBankError(f"{p}: answers[{i}] per_job must be true or false")
        key = _norm(question)
        if key in seen:
            raise AnswerBankError(f"{p}: answers[{i}] duplicates question {question!r}")
        seen.add(key)
        entries.append(Entry(question=question, answer=answer, per_job=per_job))
    return Bank(entries)
