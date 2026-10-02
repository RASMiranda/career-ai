"""Reproducible normalisation and dedupe keys.

The dedupe key must be stable across runs and across machines, so the algorithm
is defined here and covered by tests rather than left to a prompt.
"""

import hashlib
import re
import unicodedata

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")

# Noise that platforms add to titles and that should not create a "new" job.
_TITLE_NOISE = re.compile(
    r"\b(m/f/d|m/w/d|h/f|f/m/d|urgent|hiring|remote|100% remote|freelance|contract|"
    r"fulltime|full time|part time|w2|c2c)\b"
)


def norm_text(value: str) -> str:
    """Lowercase, strip accents, drop punctuation, collapse whitespace."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = _TITLE_NOISE.sub(" ", value)
    value = _PUNCT.sub(" ", value)
    return _WS.sub(" ", value).strip()


def candidate_key(source: str, source_id: str, title: str, company: str) -> str:
    """Prefer a stable source identifier; fall back to title|company hash.

    The fallback is what makes the same job arriving from two boards collapse
    into one candidate.
    """
    if source_id:
        basis = f"src:{norm_text(source)}:{source_id.strip()}"
    else:
        basis = f"tc:{norm_text(title)}|{norm_text(company)}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def is_http_url(url: str) -> bool:
    return isinstance(url, str) and url.startswith(("http://", "https://"))


def truncate(text: str, limit: int = 1500) -> str:
    """Descriptions are trimmed before they reach the model: they are the
    largest and least trustworthy part of the payload."""
    if not text:
        return ""
    text = _WS.sub(" ", re.sub(r"<[^>]+>", " ", text)).strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " ..."
