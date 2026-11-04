"""The gate between 'a good match exists' and 'something may be submitted'.

Design rules (do not weaken without thinking hard):

* Submission is off unless authorization.yaml has master_switch true with a dated acknowledgement (ADR-042).
* LinkedIn Easy Apply may run in auto only with its own enabled flag, mode auto and a dated LinkedIn
  acknowledgement, and it has its own caps. Every other adapter uses the general caps.
* The blacklist and one application per company per window are checked before any submit.
"""

from ..blacklist import Blacklist, canon
from . import authz
from .adapters import detect_ats
from .queue import TRACKING, Queue

RANK = {"low": 0, "medium": 1, "high": 2}

DEFAULTS = {
    "mode": "manual",           # off | manual | assisted | auto
    "delay_seconds": 30,
    "follow_up_days": 7,        # days after applying without a reply before a follow-up is due
    "auto": {
        "min_fit": 85,
        "min_confidence": "high",
        "allowed_tiers": ["core"],
        "max_per_day": 3,
        "max_per_week": 10,
        "one_per_company_days": 30,
        "allowed_adapters": ["greenhouse", "lever", "ashby"],
    },
}


def apply_cfg(cfg: dict) -> dict:
    out = {**DEFAULTS, **(cfg.get("apply") or {})}
    out["auto"] = {**DEFAULTS["auto"], **((cfg.get("apply") or {}).get("auto") or {})}
    return out


def auto_switch_on(auth: dict) -> bool:
    return authz.master_switch_on(auth)


def allowed_adapters(acfg: dict, auth: dict) -> list[str]:
    return authz.allowed_adapters(acfg["auto"]["allowed_adapters"], auth)


def adapter_caps(acfg: dict, auth: dict, adapter: str | None) -> dict:
    """LinkedIn has its own caps (ADR-042); every other adapter uses the general ones."""
    return authz.linkedin_caps(auth) if adapter == authz.LINKEDIN else acfg["auto"]


def _submitted(queue: Queue, days: float, adapter: str | None) -> list[dict]:
    rows = queue.submitted_within(days)
    if adapter is None:
        return rows
    return [r for r in rows if detect_ats(r.get("url", "")) == adapter]


def remaining_quota(acfg: dict, queue: Queue, adapter: str | None = None, caps: dict | None = None) -> int:
    a = caps or acfg["auto"]
    return max(0, min(a["max_per_day"] - len(_submitted(queue, 1, adapter)),
                      a["max_per_week"] - len(_submitted(queue, 7, adapter))))


def already_applied(item: dict) -> bool:
    """Dedup: a record with applied_at is an application that went out. It is never submitted again,
    and the live page is not re-checked to find out."""
    return bool(item.get("applied_at")) or any(a.get("applied_at") for a in item.get("attempts", []))


def recently_applied(queue: Queue, company: str, days: int) -> bool:
    target = canon(company)
    return any(canon(i.get("company", "")) == target
               for i in queue.submitted_within(days) + [
                   x for x in queue.by_status("done", "filled", *TRACKING)])


def initial_status(item: dict, acfg: dict, auth: dict, queue: Queue,
                   blacklist: Blacklist) -> tuple[str, list[str]]:
    """Decide the starting status for a freshly queued match, with reasons."""
    hit = blacklist.match(item)
    if hit:
        return "skipped", [f"blacklisted company ({hit})"]

    mode, a, notes = acfg["mode"], acfg["auto"], []
    if mode in ("manual", "off"):
        return "queued", ["manual mode: apply yourself or approve explicitly"]

    ats = detect_ats(item.get("url", ""))
    caps = adapter_caps(acfg, auth, ats)
    if item["fit"] < a["min_fit"]:
        notes.append(f"fit {item['fit']} below {a['min_fit']}")
    if RANK[item["confidence"]] < RANK[a["min_confidence"]]:
        notes.append(f"confidence {item['confidence']} below {a['min_confidence']}")
    if item.get("tier") not in a["allowed_tiers"]:
        notes.append(f"tier {item.get('tier')!r} not auto-eligible")
    if ats is None or ats not in allowed_adapters(acfg, auth):
        if ats == authz.LINKEDIN:
            _, why = authz.linkedin_may_auto(auth)
            notes.append("adapter linkedin_easy_apply not auto-enabled: " + "; ".join(why))
        else:
            notes.append("no automatic adapter for this site")
    if recently_applied(queue, item.get("company", ""), caps["one_per_company_days"]):
        notes.append("already applied to this company recently")
    if mode == "auto" and not auto_switch_on(auth):
        notes.append("auto-submit master switch is off in authorization.yaml")

    return ("queued", notes) if notes else ("approved", ["passed auto policy"])
