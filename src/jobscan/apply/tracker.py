"""Application tracker: what happened after an application went out.

The queue already knows what was applied to (``submitted`` by the runner, ``done``
by hand). This adds what came back, so the daily summary can show a funnel and
the applications that have gone quiet:

    replied -> interview -> offer          rejected | withdrawn can follow any of them

Nothing here contacts anyone. A follow-up is only *due*: the human sends it, from
the draft that ``jobscan.kit`` wrote, or by hand.
"""

from datetime import date, datetime, timedelta, timezone

from .queue import APPLIED, TRACKING, Queue

# Stages a follow-up still makes sense for: applied, nobody has answered.
AWAITING = ("submitted", "done")
FUNNEL = ("submitted", "done", "replied", "interview", "offer", "rejected", "withdrawn")
DEFAULT_FOLLOW_UP_DAYS = 7


def _applied_on(item: dict) -> date | None:
    # Items marked done before applied_at existed: the status change was the day it was applied.
    stamp = item.get("applied_at") or item.get("submitted_at") or (
        item.get("updated") if item.get("status") == "done" else None)
    if not stamp:
        return None
    return datetime.fromisoformat(stamp).astimezone(timezone.utc).date()


def track(queue: Queue, key: str, status: str, note: str = "", follow_up: str = "") -> dict:
    """Record a reply, interview, offer, rejection or withdrawal on an applied item."""
    if status not in TRACKING:
        raise ValueError(f"status must be one of {', '.join(TRACKING)}")
    item = queue.items[key]
    if item.get("status") not in APPLIED:
        raise ValueError(f"{item['title']} — {item['company']} is {item.get('status')!r}: "
                         f"record the application first (`done` if you applied yourself)")
    extra = {}
    if follow_up:
        try:
            date.fromisoformat(follow_up)
        except ValueError:
            raise ValueError(f"--follow-up must be a date like 2026-10-20, not {follow_up!r}")
        extra["follow_up_on"] = follow_up
    queue.set(key, status, **extra)
    if note.strip():
        item.setdefault("notes", []).append(
            {"on": item["updated"], "status": status, "text": note.strip()[:500]})
    return item


def mark_followed_up(queue: Queue, key: str) -> dict:
    item = queue.items[key]
    if item.get("status") not in AWAITING:
        raise ValueError(f"{item['title']} — {item['company']} is {item.get('status')!r}: "
                         f"a follow-up applies to an application nobody has answered")
    item["followed_up_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    item.pop("follow_up_on", None)
    return item


def follow_ups_due(queue: Queue, today: date | None = None, days: int = DEFAULT_FOLLOW_UP_DAYS,
                   profile: str | None = None) -> list[dict]:
    """Applications with no answer after ``days`` (or after the date the human set), oldest first."""
    today = today or datetime.now(timezone.utc).date()
    due = []
    for item in queue.by_status(*AWAITING):
        if profile is not None and item.get("profile") != profile:
            continue
        if item.get("followed_up_at"):
            continue
        if item.get("follow_up_on"):
            when = date.fromisoformat(item["follow_up_on"])
        else:
            applied = _applied_on(item)
            if applied is None:
                continue
            when = applied + timedelta(days=days)
        if when <= today:
            due.append(item)
    return sorted(due, key=lambda i: (_applied_on(i) or today, -i.get("fit", 0)))


def funnel(queue: Queue, profile: str | None = None) -> dict[str, int]:
    """Count of applied items by stage; empty when nothing was applied to."""
    counts = {s: 0 for s in FUNNEL}
    for item in queue.items.values():
        if item.get("status") in counts and (profile is None or item.get("profile") == profile):
            counts[item["status"]] += 1
    return counts if any(counts.values()) else {}


def response_rate(counts: dict[str, int]) -> int | None:
    """Percent of applications that got any answer (reply, interview, offer or rejection)."""
    total = sum(counts.values()) - counts.get("withdrawn", 0)
    if not total:
        return None
    answered = sum(counts.get(s, 0) for s in ("replied", "interview", "offer", "rejected"))
    return round(100 * answered / total)
