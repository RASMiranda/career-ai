"""Application queue, stored in the private data repo.

status: queued -> approved -> submitted | filled | failed
        queued -> done (you applied by hand) | skipped
        submitted | done -> replied -> interview -> offer      (tracker, see tracker.py)
        submitted | done | replied | interview -> rejected | withdrawn
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..state import _read, _write

# After an application went out the tracker records what came back.
TRACKING = ("replied", "interview", "offer", "rejected", "withdrawn")
STATUSES = ("queued", "approved", "filled", "submitted", "failed", "done", "skipped", *TRACKING)
# Statuses in which an application exists, however it ended.
APPLIED = ("submitted", "done", *TRACKING)


def now() -> datetime:
    return datetime.now(timezone.utc)


class Queue:
    def __init__(self, root: Path):
        self.path = root / "applications" / "queue.json"
        self.items: dict = _read(self.path, {}).get("items", {})

    def save(self) -> None:
        _write(self.path, {"items": self.items})

    def has(self, key: str) -> bool:
        return key in self.items

    def add(self, key: str, record: dict) -> None:
        self.items[key] = {"candidate_key": key, "created": now().isoformat(timespec="seconds"),
                           "attempts": [], **record}

    def resolve(self, prefix: str) -> str:
        hits = [k for k in self.items if k.startswith(prefix)]
        if len(hits) != 1:
            raise KeyError(f"{prefix!r} matches {len(hits)} items")
        return hits[0]

    def set(self, key: str, status: str, **extra) -> None:
        assert status in STATUSES, status
        item = self.items[key]
        item["status"] = status
        item["updated"] = now().isoformat(timespec="seconds")
        if status == "submitted":
            item["submitted_at"] = item["updated"]
        if status in ("submitted", "done"):
            item.setdefault("applied_at", item["updated"])
        item.update(extra)

    def by_status(self, *statuses) -> list[dict]:
        return [i for i in self.items.values() if i.get("status") in statuses]

    def submitted_within(self, days: float) -> list[dict]:
        cutoff = now() - timedelta(days=days)
        return [i for i in self.items.values()
                if i.get("submitted_at") and datetime.fromisoformat(i["submitted_at"]) >= cutoff]
