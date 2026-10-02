import pytest
from jobscan.validate import validate

AUTH = {"active": True}
CANDS = {"candidates": [
    {"candidate_key": "k1", "title": "A", "company": "X", "url": "https://x.test/1"},
    {"candidate_key": "k2", "title": "B", "company": "Y", "url": ""},
]}


def d(key, **over):
    base = {"candidate_key": key, "fit": 80, "tier": "core", "confidence": "high",
            "disposition": "discarded", "why": "reason"}
    base.update(over)
    return base


def test_happy_path():
    ok, problems = validate(CANDS, [d("k1", disposition="email"), d("k2")], AUTH)
    assert problems == [] and len(ok) == 2


def test_every_candidate_needs_exactly_one_decision():
    _, problems = validate(CANDS, [d("k1")], AUTH)
    assert any("no decision" in p for p in problems)


def test_duplicate_decisions_are_rejected():
    _, problems = validate(CANDS, [d("k1"), d("k1"), d("k2")], AUTH)
    assert any("duplicate" in p for p in problems)


def test_email_requires_a_valid_link():
    _, problems = validate(CANDS, [d("k1"), d("k2", disposition="email")], AUTH)
    assert any("no valid http" in p for p in problems)


def test_low_confidence_cannot_be_emailed():
    _, problems = validate(
        CANDS, [d("k1", disposition="email", confidence="low"), d("k2")], AUTH)
    assert any("low confidence" in p for p in problems)


@pytest.mark.parametrize("bad", [-1, 101, "90", None])
def test_fit_must_be_int_0_100(bad):
    _, problems = validate(CANDS, [d("k1", fit=bad), d("k2")], AUTH)
    assert any("fit must be" in p or "missing fields" in p for p in problems)


def test_inactive_authorization_blocks_everything():
    _, problems = validate(CANDS, [d("k1"), d("k2")], {"active": False})
    assert any("active is not true" in p for p in problems)


def _cfg(**notify):
    return {"profiles": [{"id": "p", "notify": notify}]}


def test_recipients_come_from_each_profile_not_authorization():
    _, problems = validate(CANDS, [d("k1"), d("k2")], AUTH,
                           cfg=_cfg(email=["me@mail.test"]))
    assert problems == []


@pytest.mark.parametrize("notify, needle", [
    ({}, "no notify.email"),
    ({"email": []}, "no notify.email"),
    ({"email": ["not-an-address"]}, "invalid address"),
    ({"email": ["REPLACE-WITH-YOUR-EMAIL@example.com"]}, "placeholder"),
])
def test_profile_without_a_usable_recipient_fails(notify, needle):
    _, problems = validate(CANDS, [d("k1"), d("k2")], AUTH, cfg=_cfg(**notify))
    assert any(needle in p for p in problems)
