import json

import pytest

from jobscan import bank
from jobscan.bank import ApplyOutcome, AnswerBankError, ApplyOutcomeError

HEADER = "version: 2\nanswers:\n"

GOOD = HEADER + """\
  - key: how_heard
    match: ["how did you hear about us", "how did you hear about this job"]
    answer: "Option A"
    scope: standing
    source: rui_statement
    decided_on: 2026-11-04
    quote: "Always Option A."
  - key: relative_at_company
    match: ["are you a relative of anyone at this company"]
    answer: "No"
    scope: standing
    source: rui_statement
    decided_on: 2026-11-04
    quote: ""
  - key: per_job_note
    match: ["what is your motivation for this role"]
    answer: "Draft text"
    scope: per_job
    source: cv
    decided_on: 2026-11-04
    quote: ""
  - key: empty_one
    match: ["postal code"]
    answer: ""
    scope: standing
    source: rates
    decided_on: 2026-11-04
    quote: ""
  - key: name_on_forms
    match: ["legal name"]
    answer: CONFLICT
    scope: standing
    source: rui_statement
    decided_on: 2026-11-04
    quote: ""
    conflicts:
      - {value: "First Option", source: "skill bank"}
      - {value: "Second Option", source: "profile"}
  - key: authorised_to_work
    match: ["are you authorized to work in this country"]
    answer: "Yes"
    scope: standing
    source: rui_statement
    decided_on: 2026-11-04
    quote: "Always say I have work auth"
  - key: sponsorship
    match: ["will you now or in the future require sponsorship"]
    answer: "No"
    scope: standing
    source: rui_statement
    decided_on: 2026-11-04
    quote: ""
"""

ACK = {"work_auth_standing": {"acknowledged_on": "2026-11-05"}}


def write(tmp_path, text, name="answer_bank.yaml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def bank_obj(tmp_path):
    return bank.load(write(tmp_path, GOOD))


def look(bank_obj, q, **kw):
    return bank.lookup(q, bank=bank_obj, **kw)


# ---- lookup ----------------------------------------------------------------------------------

def test_exact_match_returns_answer(bank_obj):
    r = look(bank_obj, "how did you hear about us")
    assert (r.status, r.value, r.layer) == (bank.ANSWER, "Option A", "answer_bank")


def test_normalised_match_ignores_case_punctuation_and_spacing(bank_obj):
    r = look(bank_obj, "  HOW did you hear   about us??  ")
    assert r.status == bank.ANSWER and r.value == "Option A"


def test_miss_returns_needs_answer(bank_obj):
    r = look(bank_obj, "favourite colour")
    assert r.status == bank.NEEDS_ANSWER and r.value is None


def test_per_job_entry_is_not_returned_as_standing(bank_obj):
    r = look(bank_obj, "what is your motivation for this role")
    assert r.status == bank.NEEDS_ANSWER
    assert "Draft text" not in repr(r)


def test_empty_answer_means_unknown(bank_obj):
    r = look(bank_obj, "postal code")
    assert r.status == bank.NEEDS_ANSWER and r.reason == "unknown in answer bank"


def test_conflict_returns_both_values(bank_obj):
    r = look(bank_obj, "legal name")
    assert r.status == bank.CONFLICT
    assert r.options == (("First Option", "skill bank"), ("Second Option", "profile"))
    assert r.value is None


def test_bank_answers_before_profile_and_knowledge(bank_obj):
    profile = {"answers": {"how did you hear about us": "Profile value"}}
    knowledge = {"how did you hear about us": "Knowledge value"}
    r = look(bank_obj, "how did you hear about us", profile=profile, knowledge=knowledge)
    assert r.value == "Option A" and r.layer == "answer_bank"


def test_profile_answers_used_when_bank_misses(bank_obj):
    profile = {"answers": {"notice period": "Example notice"}}
    r = look(bank_obj, "notice period", profile=profile)
    assert (r.status, r.value, r.layer) == (bank.ANSWER, "Example notice", "profile")


def test_profile_empty_value_is_a_miss(bank_obj):
    r = look(bank_obj, "notice period", profile={"answers": {"notice period": ""}})
    assert r.status == bank.NEEDS_ANSWER


def test_knowledge_used_after_profile(bank_obj, tmp_path):
    folder = tmp_path / "01-knowledge"
    folder.mkdir()
    (folder / "notes.md").write_text("# Notes\n\n## Languages spoken\n\nExample language line.\n", encoding="utf-8")
    knowledge = bank.load_knowledge(folder)
    r = look(bank_obj, "languages spoken", knowledge=knowledge)
    assert (r.status, r.value, r.layer) == (bank.ANSWER, "Example language line.", "knowledge")


def test_knowledge_heading_resets_on_next_section(tmp_path):
    folder = tmp_path / "k"
    folder.mkdir()
    (folder / "a.md").write_text("## First\n\nText one.\n# Other\nNot an answer.\n", encoding="utf-8")
    assert bank.load_knowledge(folder) == {"first": "Text one."}


# ---- policy guard ----------------------------------------------------------------------------

def test_work_auth_refused_until_acknowledged(bank_obj):
    r = look(bank_obj, "are you authorized to work in this country", authorization={})
    assert r.status == bank.NEEDS_ANSWER
    assert "not acknowledged" in r.reason


def test_work_auth_answered_once_acknowledged(bank_obj):
    r = look(bank_obj, "are you authorized to work in this country", authorization=ACK)
    assert (r.status, r.value) == (bank.ANSWER, "Yes")


def test_sponsorship_refused_until_acknowledged(bank_obj):
    assert look(bank_obj, "will you now or in the future require sponsorship").status == bank.NEEDS_ANSWER
    assert look(bank_obj, "will you now or in the future require sponsorship",
                authorization=ACK).value == "No"


def test_work_auth_in_profile_also_needs_acknowledgement():
    profile = {"answers": {"authorized to work": "Yes"}}
    assert bank.lookup("authorized to work", bank=bank.Bank(()), profile=profile).status == bank.NEEDS_ANSWER
    assert bank.lookup("authorized to work", bank=bank.Bank(()), profile=profile,
                       authorization=ACK).value == "Yes"


@pytest.mark.parametrize("question", [
    "Do you attest that the information above is true under oath?",
    "Please confirm your I-9 status",
    "What is your citizenship?",
    "Do you hold an active security clearance?",
])
def test_always_human_questions_never_answered(bank_obj, question):
    r = look(bank_obj, question, authorization=ACK,
             profile={"answers": {question: "Would be wrong"}})
    assert r.status == bank.NEEDS_ANSWER
    assert r.value is None


def test_always_human_wins_over_an_exact_bank_entry(tmp_path):
    text = HEADER + """\
  - key: citizen_status
    match: ["citizenship status"]
    answer: "Option Z"
    scope: standing
    source: rui_statement
    decided_on: 2026-11-04
    quote: ""
"""
    b = bank.load(write(tmp_path, text))
    r = look(b, "citizenship status", authorization=ACK)
    assert r.status == bank.NEEDS_ANSWER and r.value is None


# ---- loader ----------------------------------------------------------------------------------

def test_good_bank_loads(bank_obj):
    assert len(bank_obj) == 7
    assert bank_obj.find("Legal Name").key == "name_on_forms"


@pytest.mark.parametrize("text, message", [
    ("version: 1\nanswers: []\n", "version must be 2"),
    (HEADER + "  - key: a\n    match: [x]\n    answer: y\n    scope: nope\n    source: cv\n"
              "    decided_on: 2026-01-01\n    quote: ''\n", "scope must be"),
    (HEADER + "  - key: a\n    match: [x]\n    answer: y\n    scope: standing\n    source: web\n"
              "    decided_on: 2026-01-01\n    quote: ''\n", "source must be"),
    (HEADER + "  - key: a\n    match: [x]\n    answer: y\n    scope: standing\n    source: cv\n"
              "    decided_on: not-a-date\n    quote: ''\n", "ISO date"),
    (HEADER + "  - key: a\n    match: [x]\n    answer: y\n    scope: standing\n    source: cv\n"
              "    decided_on: 2026-01-01\n", "missing required keys"),
    (HEADER + "  - key: a\n    match: [x]\n    answer: y\n    scope: standing\n    source: cv\n"
              "    decided_on: 2026-01-01\n    quote: ''\n    extra: 1\n", "unknown keys"),
    (HEADER + "  - key: A-B\n    match: [x]\n    answer: y\n    scope: standing\n    source: cv\n"
              "    decided_on: 2026-01-01\n    quote: ''\n", "lowercase letters"),
])
def test_loader_rejects_bad_entries(tmp_path, text, message):
    with pytest.raises(AnswerBankError, match=message):
        bank.load(write(tmp_path, text))


def test_loader_rejects_duplicate_key(tmp_path):
    one = GOOD.split("  - key: relative_at_company")[0]
    text = one + "  - key: how_heard\n    match: [other phrase]\n    answer: x\n    scope: standing\n" \
                 "    source: cv\n    decided_on: 2026-01-01\n    quote: ''\n"
    with pytest.raises(AnswerBankError, match="duplicate key"):
        bank.load(write(tmp_path, text))


def test_loader_rejects_phrase_used_twice(tmp_path):
    text = HEADER + """\
  - key: one
    match: ["same question"]
    answer: "A"
    scope: standing
    source: cv
    decided_on: 2026-01-01
    quote: ""
  - key: two
    match: ["Same Question!"]
    answer: "B"
    scope: standing
    source: cv
    decided_on: 2026-01-01
    quote: ""
"""
    with pytest.raises(AnswerBankError, match="used by two entries"):
        bank.load(write(tmp_path, text))


def test_conflict_needs_conflict_answer_and_two_options(tmp_path):
    base = HEADER + "  - key: c\n    match: [q]\n    scope: standing\n    source: cv\n" \
                    "    decided_on: 2026-01-01\n    quote: ''\n"
    with pytest.raises(AnswerBankError, match="at least two"):
        bank.load(write(tmp_path, base + "    answer: CONFLICT\n    conflicts:\n      - {value: a, source: s}\n"))
    with pytest.raises(AnswerBankError, match="must be CONFLICT"):
        bank.load(write(tmp_path, base + "    answer: a\n    conflicts:\n"
                                         "      - {value: a, source: s}\n      - {value: b, source: t}\n"))
    with pytest.raises(AnswerBankError, match="no conflicts are listed"):
        bank.load(write(tmp_path, base + "    answer: CONFLICT\n"))


def test_loader_errors_never_show_an_answer_value(tmp_path):
    secret_value = "VALUE-THAT-MUST-NOT-LEAK"
    text = HEADER + f"  - key: bad\n    match: [q]\n    answer: '{secret_value}'\n    scope: standing\n" \
                    f"    source: web\n    decided_on: 2026-01-01\n    quote: ''\n"
    with pytest.raises(AnswerBankError) as exc:
        bank.load(write(tmp_path, text))
    assert secret_value not in str(exc.value)


def test_loader_rejects_non_text_answer(tmp_path):
    text = HEADER + "  - key: n\n    match: [q]\n    answer: 15\n    scope: standing\n    source: cv\n" \
                    "    decided_on: 2026-01-01\n    quote: ''\n"
    with pytest.raises(AnswerBankError, match="answer must be text"):
        bank.load(write(tmp_path, text))


# ---- apply-run record ------------------------------------------------------------------------

def outcome(**kw):
    base = dict(job_id="1234", employer="Example Co", role="Engineer", site="greenhouse",
                status="SUBMITTED", verified_by="confirmation_url", ts="2026-11-04")
    base.update(kw)
    return ApplyOutcome(**base)


def test_outcome_appends_to_site_and_date_file(tmp_path):
    path = bank.append_outcome(outcome(), data=str(tmp_path))
    assert path == tmp_path / "logs" / "apply" / "greenhouse-2026-11-04.jsonl"
    bank.append_outcome(outcome(job_id="5678"), data=str(tmp_path))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["job_id"] for line in lines] == ["1234", "5678"]
    assert set(json.loads(lines[0])) == {"job_id", "employer", "role", "site", "status", "verified_by", "ts"}


def test_outcome_redacts_query_strings_and_fragments(tmp_path):
    path = bank.append_outcome(
        outcome(role="see https://example.com/confirm?token=SECRET123#frag now",
                employer="Ex", ts="2026-11-04T10:00:00Z"),
        data=str(tmp_path))
    text = path.read_text(encoding="utf-8")
    assert "SECRET123" not in text and "frag" not in text
    assert "https://example.com/confirm now" in json.loads(text)["role"]


@pytest.mark.parametrize("kw, message", [
    (dict(status="DONE"), "status must be"),
    (dict(verified_by="email"), "verified_by must be"),
    (dict(verified_by=""), "must say how it was verified"),
    (dict(site="Green House"), "lowercase slug"),
    (dict(ts="yesterday"), "ISO date"),
    (dict(job_id=" "), "job_id is required"),
])
def test_outcome_rejects_bad_fields(tmp_path, kw, message):
    with pytest.raises(ApplyOutcomeError, match=message):
        bank.append_outcome(outcome(**kw), data=str(tmp_path))


def test_non_submitted_outcome_needs_no_verifier(tmp_path):
    path = bank.append_outcome(outcome(status="SKIPPED", verified_by=""), data=str(tmp_path))
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "SKIPPED"
