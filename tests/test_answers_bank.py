import pytest

from jobscan import answers
from jobscan.answers import AnswerBankError

BANK = """\
version: 1
answers:
  - question: "Are you a family member or relative of anyone at this company?"
    answer: "No"
    per_job: false
  - question: "Do you have the right to work in the country of this role?"
    answer: "I can work in the EU."
  - question: "Do you have the right to work in the country of this role? (standing)"
    answer: "I can work in the EU."
    per_job: false
  - question: "Have you ever been convicted of a criminal offence?"
    answer: "No"
    per_job: false
  - question: "Background check consent"
    answer: ""
  - question: "Postal address"
    answer: ""
"""


def write(tmp_path, text):
    p = tmp_path / "answer-bank.yaml"
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def bank(tmp_path):
    return answers.load(write(tmp_path, BANK))


def test_exact_match_ignores_case_spacing_and_punctuation(bank):
    assert bank.find("are you a family member or relative of anyone at this company") == "No"
    assert bank.find("Are you a family member or relative of anyone at this company?  ") == "No"


def test_unknown_question_is_none_never_a_guess(bank):
    assert bank.find("How many years of Kotlin do you have?") is None
    # a near miss is not a match
    assert bank.find("Are you a family member of anyone at this company?") is None


def test_empty_answer_means_unknown(bank):
    assert bank.find("Postal address") is None
    assert bank.find("Background check consent") is None


def test_refused_topic_without_standing_flag_is_none(bank):
    # exact entry exists but per_job defaults to true: the human is asked
    assert bank.find("Do you have the right to work in the country of this role?") is None


def test_refused_topic_with_per_job_false_is_answered(bank):
    assert bank.find("Do you have the right to work in the country of this role? (standing)") \
        == "I can work in the EU."
    assert bank.find("Have you ever been convicted of a criminal offence?") == "No"


def test_refused_topic_not_in_bank_is_none(bank):
    assert bank.find("Are you legally authorized to work in the United States?") is None
    assert bank.find("Do you consent to a background check?") is None
    assert bank.find("Do you require visa sponsorship?") is None
    assert bank.find("Do you have a criminal record?") is None


def test_ordinary_question_with_default_flag_is_answered(bank):
    # per_job only matters for refused topics; an ordinary standing question is answered as written
    assert bank.find("Are you a family member or relative of anyone at this company?") == "No"


def test_load_fails_on_missing_required_keys(tmp_path):
    with pytest.raises(AnswerBankError, match="missing required key 'answer'"):
        answers.load(write(tmp_path, 'version: 1\nanswers:\n  - question: "Phone"\n'))
    with pytest.raises(AnswerBankError, match="missing required key 'question'"):
        answers.load(write(tmp_path, 'version: 1\nanswers:\n  - answer: "x"\n'))


def test_load_fails_on_bad_structure(tmp_path):
    with pytest.raises(AnswerBankError, match="version must be 1"):
        answers.load(write(tmp_path, "answers: []\n"))
    with pytest.raises(AnswerBankError, match="answers must be a list"):
        answers.load(write(tmp_path, "version: 1\nanswers: {}\n"))
    with pytest.raises(AnswerBankError, match="not found"):
        answers.load(tmp_path / "missing.yaml")
    with pytest.raises(AnswerBankError, match="not valid YAML"):
        answers.load(write(tmp_path, "version: [unclosed\n"))


def test_bare_yaml_values_are_refused_so_No_is_not_read_as_false(tmp_path):
    with pytest.raises(AnswerBankError, match="must be quoted text"):
        answers.load(write(tmp_path, 'version: 1\nanswers:\n  - question: "Family?"\n    answer: No\n'))


def test_duplicate_question_and_bad_per_job_are_refused(tmp_path):
    dup = 'version: 1\nanswers:\n  - {question: "Q?", answer: "a"}\n  - {question: "q", answer: "b"}\n'
    with pytest.raises(AnswerBankError, match="duplicates"):
        answers.load(write(tmp_path, dup))
    with pytest.raises(AnswerBankError, match="per_job"):
        answers.load(write(tmp_path, 'version: 1\nanswers:\n  - {question: "Q?", answer: "a", per_job: "no"}\n'))


def test_empty_answers_list_is_valid(tmp_path):
    assert len(answers.load(write(tmp_path, "version: 1\nanswers: []\n"))) == 0
