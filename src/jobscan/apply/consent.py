"""Consent and declaration fields: the adapter never answers these, it stops and hands the job back.

A consent box, a privacy-policy acceptance or a signed declaration is a promise the applicant makes in
their own name. No pre-approved answer, drafted answer or posting text may tick it (ADR-019, ARCHITECTURE §6).
Legal and work-authorisation questions are not classified here: they keep their existing stop
(UNKNOWN_REQUIRED_FIELD until the owner answers).
"""

import re
from enum import Enum


class FieldClass(str, Enum):
    ORDINARY = "ordinary"
    CONSENT_PENDING = "consent_pending"


_CONSENT = re.compile(r"""
    privacy\s+(policy|notice|statement)
  | \bnon[\s-]?disclosure\b | \bnda\b
  | application\s+declaration
  | \bi\s+agree\b | \bi\s+consent\b | \bi\s+acknowledge\b
  | terms\s+(and|&)\s+conditions
  | data\s+processing\s+consent
""", re.VERBOSE | re.IGNORECASE)


def classify_field(label: str, kind: str) -> FieldClass:
    """CONSENT_PENDING when the label asks for a consent, declaration or acceptance, else ORDINARY.

    ``kind`` (text, checkbox, radio, select...) does not change the result: a consent is a consent
    whatever control draws it. Matching is case-insensitive on whole phrases.
    """
    text = " ".join((label or "").split())
    return FieldClass.CONSENT_PENDING if _CONSENT.search(text) else FieldClass.ORDINARY
