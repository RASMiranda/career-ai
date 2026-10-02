"""Configurable company blacklist.

Matching is deliberately forgiving about spelling ("Micro 1", "MICRO1 Inc.",
"micro1.ai") and strict about word boundaries ("Aligner" is not "Alignerr").

Applied three times, on purpose:
  1. collect  -> blacklisted jobs never reach the model (saves tokens)
  2. validate -> fails the run if one slipped through (config changed mid-run)
  3. apply    -> never queue or submit to a blacklisted company
"""

import re
import unicodedata
from urllib.parse import urlparse

_LEGAL = re.compile(
    r"\b(inc|llc|ltd|limited|gmbh|sa|sl|lda|unipessoal|bv|ag|plc|corp|"
    r"corporation|co|company|oy|ab|pte|pty|sarl|srl)\b"
)
_PUNCT = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")


def canon(name: str) -> str:
    """Lowercase, strip accents, drop punctuation and legal suffixes.
    Unlike normalize.norm_text this keeps words like 'remote' — they can be a
    real company name."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = _PUNCT.sub(" ", s)
    s = _LEGAL.sub(" ", s)
    return _WS.sub(" ", s).strip()


def _squash(s: str) -> str:
    return s.replace(" ", "")


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


class Blacklist:
    def __init__(self, entries: list | None = None, match_description: bool = False):
        self.match_description = match_description
        self.entries = []
        for raw in entries or []:
            entry = {"name": raw} if isinstance(raw, str) else dict(raw)
            name = entry.get("name", "").strip()
            if not name:
                continue
            names = [name, *entry.get("aliases", [])]
            self.entries.append({
                "name": name,
                "reason": entry.get("reason", ""),
                "spaced": [canon(n) for n in names if canon(n)],
                "squashed": {_squash(canon(n)) for n in names if canon(n)},
                "domains": [d.lower().removeprefix("www.") for d in entry.get("domains", [])],
            })

    @classmethod
    def from_config(cls, cfg: dict, profile_id: str | None = None) -> "Blacklist":
        """Global list plus an optional per-profile list."""
        bl = cfg.get("blacklist") or {}
        entries = list(bl.get("companies") or [])
        for profile in cfg.get("profiles", []):
            if profile.get("id") == profile_id:
                entries += list((profile.get("blacklist") or {}).get("companies") or [])
        return cls(entries, bool(bl.get("match_description", False)))

    def __len__(self) -> int:
        return len(self.entries)

    def match(self, job: dict) -> str | None:
        """Return the blacklist entry name that matches, or None."""
        company = canon(job.get("company", ""))
        host = _host(job.get("url", ""))
        text = canon(f"{job.get('title','')} {job.get('description','')}") \
            if self.match_description else ""
        for e in self.entries:
            if company:
                if _squash(company) in e["squashed"]:
                    return e["name"]
                for spaced in e["spaced"]:
                    if re.search(rf"(?<![a-z0-9]){re.escape(spaced)}(?![a-z0-9])", company):
                        return e["name"]
            if host and any(host == d or host.endswith("." + d) for d in e["domains"]):
                return e["name"]
            if text:
                for spaced in e["spaced"]:
                    if re.search(rf"(?<![a-z0-9]){re.escape(spaced)}(?![a-z0-9])", text):
                        return e["name"]
        return None
