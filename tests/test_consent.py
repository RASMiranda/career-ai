"""Consent and declaration detection: which field labels the adapter must never answer."""

from jobscan.apply.consent import FieldClass, classify_field

CONSENT_LABELS = [
    "I agree to the privacy policy *",
    "Privacy Policy",
    "Please read and accept our privacy notice",
    "Privacy statement acknowledgement",
    "NDA",
    "Do you accept the NDA?",
    "Non-disclosure agreement",
    "Non disclosure agreement",
    "Application declaration",
    "I consent to the processing of my personal data",
    "I acknowledge that I have read the job description",
    "Terms and conditions",
    "Terms & Conditions",
    "Data processing consent",
    "I AGREE to the terms",
    "i consent",
]

ORDINARY_LABELS = [
    "Are you comfortable commuting?",
    "Are you comfortable with on-call rotation?",
    "Do you agree to relocate?",          # 'agree' without 'I' is a question about relocation, not consent
    "I agreed to the schedule",           # whole phrase only: 'agreed' is not 'agree'
    "Acknowledgement of the notice period",
    "Ndaba",                              # 'nda' inside a word
    "First name *",
    "Years of Java experience",
    "Why do you want to work here?",
    "Salary expectations",
    "Work authorisation in the EU",       # legal: keeps its own stop, not a consent
    "",
]


def test_consent_labels_are_consent_pending_whatever_the_control():
    for label in CONSENT_LABELS:
        for kind in ("text", "checkbox", "radio", "textarea", "select"):
            assert classify_field(label, kind) is FieldClass.CONSENT_PENDING, (label, kind)


def test_ordinary_labels_are_not_consent():
    for label in ORDINARY_LABELS:
        assert classify_field(label, "text") is FieldClass.ORDINARY, label
        assert classify_field(label, "checkbox") is FieldClass.ORDINARY, label


def test_none_and_stray_whitespace_are_handled():
    assert classify_field(None, "text") is FieldClass.ORDINARY
    assert classify_field("I\n  agree", "checkbox") is FieldClass.CONSENT_PENDING
