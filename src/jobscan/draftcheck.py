"""What a model-written draft may never contain, shared by every drafting step.

The posting (or the form) the draft answers is untrusted text, and a draft is the thing most
likely to be pasted or submitted without being read word for word. So code rejects any draft
carrying a link, an address, a phone number, markup or an unfilled placeholder.
"""

import re

BAD = [
    ("a link", re.compile(r"https?://|www\.", re.I)),
    ("an email address", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("a phone number", re.compile(r"(?<![\w])\+?\d[\d\s().-]{7,}\d(?![\w])")),
    ("HTML", re.compile(r"</?[a-zA-Z][^>]*>")),
    ("an unfilled placeholder", re.compile(
        r"\{\{|\}\}|\[[^\]\n]{0,40}(name|company|position|role|title|date|your|insert|hiring|manager)[^\]\n]{0,40}\]"
        r"|\bTODO\b|\bTBD\b|lorem ipsum|\bXXX+\b", re.I)),
]


def problems_in(text: str) -> list[str]:
    """Names of the forbidden things found in ``text`` (empty when it is clean)."""
    return [what for what, rx in BAD if rx.search(text)]
