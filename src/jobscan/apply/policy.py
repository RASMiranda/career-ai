"""The gate between 'a good match exists' and 'something may be submitted'."""

from ..blacklist import Blacklist, canon
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
    sub = auth.get("application_submission") or {}
    return bool(sub.get("allow_auto_submit")) and bool(str(sub.get("acknowledged_on") or "").strip())


def remaining_quota(acfg: dict, queue: Queue) -> int:
    a = acfg["auto"]
    return max(0, min(a["max_per_day"] - len(queue.submitted_within(1)),
                      a["max_per_week"] - len(queue.submitted_within(7))))


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

    if item["fit"] < a["min_fit"]:
        notes.append(f"fit {item['fit']} below {a['min_fit']}")
    if RANK[item["confidence"]] < RANK[a["min_confidence"]]:
        notes.append(f"confidence {item['confidence']} below {a['min_confidence']}")
    if item.get("tier") not in a["allowed_tiers"]:
        notes.append(f"tier {item.get('tier')!r} not auto-eligible")
    ats = detect_ats(item.get("url", ""))
    if ats is None or ats not in a["allowed_adapters"]:
        notes.append("no automatic adapter for this site")
    if recently_applied(queue, item.get("company", ""), a["one_per_company_days"]):
        notes.append("already applied to this company recently")
    if mode == "auto" and not auto_switch_on(auth):
        notes.append("auto-submit master switch is off in authorization.yaml")

    return ("queued", notes) if notes else ("approved", ["passed auto policy"])
