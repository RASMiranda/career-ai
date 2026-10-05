"""Deterministic triage: spend model tokens only on candidates that need judgement.

Per profile (``prefilter:`` in profile.yaml):

    prefilter:
      min_description_chars: 300   # shorter text (e.g. alert emails) always goes to the model
      require_any: [java, angular] # a described job must mention one of these (whole words)
      reject_title: ['\\bjunior\\b'] # regexes; a matching title is discarded
      max_to_score: 40             # more than this per run waits for the next run

Rejected candidates get a ``discarded`` decision written by code ("prefilter: ...");
the model never sees them. Candidates over the cap are left out of the run
entirely and are not marked seen, so they come back next time.
"""

import html
import re

from .config import ConfigError
from .cv import catalog

DEFAULT_MAX_TO_SCORE = 40
DEFAULT_MIN_DESCRIPTION = 300
EXCERPT_CHARS = 500

_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def clean(text: str) -> str:
    """Plain text: tags dropped, entities decoded, whitespace collapsed."""
    return _SPACE.sub(" ", html.unescape(_TAGS.sub(" ", text or ""))).strip()


def rules_for(profile: dict) -> dict:
    raw = profile.get("prefilter") or {}
    try:
        reject = [re.compile(p, re.I) for p in raw.get("reject_title") or []]
    except re.error as exc:
        raise ConfigError(f"profile {profile.get('id')!r}: bad prefilter.reject_title regex: {exc}")
    terms = [t for t in raw.get("require_any") or [] if str(t).strip()]
    require = re.compile("|".join(rf"(?<!\w){re.escape(str(t).strip())}(?!\w)" for t in terms), re.I) if terms else None
    return {"reject_title": reject, "require_any": require,
            "min_description_chars": int(raw.get("min_description_chars", DEFAULT_MIN_DESCRIPTION)),
            "max_to_score": int(raw.get("max_to_score", DEFAULT_MAX_TO_SCORE))}


def reject_reason(candidate: dict, rules: dict) -> str | None:
    title = candidate.get("title") or ""
    for rx in rules["reject_title"]:
        if rx.search(title):
            return f"title matches {rx.pattern}"
    description = clean(candidate.get("description"))
    if (rules["require_any"] and len(description) >= rules["min_description_chars"]
            and not rules["require_any"].search(f"{title} {description}")):
        return "none of the required terms appear"
    return None


def auto_decision(candidate: dict, reason: str) -> dict:
    return {"candidate_key": candidate["candidate_key"], "fit": 0, "tier": "radar",
            "confidence": "high", "disposition": "discarded",
            "why": f"prefilter: {reason}", "caution": "", "next_action": "None"}


def triage(payload: dict, cfg: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (auto decisions, candidates for the model, candidates deferred by the cap)."""
    rules = {p["id"]: rules_for(p) for p in cfg["profiles"]}
    default = rules_for({})
    auto, to_score, deferred, scored = [], [], [], {}
    for c in payload["candidates"]:
        pid = c.get("profile")
        r = rules.get(pid, default)
        reason = reject_reason(c, r)
        if reason:
            auto.append(auto_decision(c, reason))
        elif scored.get(pid, 0) >= r["max_to_score"]:
            deferred.append(c)
        else:
            scored[pid] = scored.get(pid, 0) + 1
            to_score.append(c)
    return auto, to_score, deferred


def render_brief(to_score: list[dict], cfg: dict, root, excerpt: int = EXCERPT_CHARS) -> str:
    """What the model reads instead of candidates.json: one short block per candidate."""
    profiles = {p["id"]: p for p in cfg["profiles"]}
    out = []
    for pid in dict.fromkeys(c.get("profile") for c in to_score):
        p = profiles.get(pid, {"id": pid})
        cvs = ", ".join(sorted(catalog(root, p))) or "none"
        out += [f"# Profile {pid}: criteria {p.get('criteria', '?')} · CV variants: {cvs}", ""]
        for c in (c for c in to_score if c.get("profile") == pid):
            text = clean(c.get("description"))
            remote = {True: "remote", False: "not remote"}.get(c.get("remote"), "remote?")
            facts = " | ".join(filter(None, [c.get("location"), remote, c.get("contract_type"),
                                             c.get("salary"), c.get("source")]))
            more = f" […+{len(text) - excerpt} chars: pipeline show {c['candidate_key']}]" if len(text) > excerpt else ""
            out += [f"## {c['candidate_key']} | {c['title']} | {c['company']}",
                    facts, (text[:excerpt] + more) if text else "(no description)", ""]
    return "\n".join(out).rstrip() + "\n"
