"""Seen-set, API budget and delivery journal.

State is persisted in the private data repo so history and criteria stay
together and neither leaks into the public code repo.
"""

import json
from datetime import date, datetime, timezone
from pathlib import Path


def _read(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)  # atomic: a crash mid-write never leaves a truncated file


class Seen:
    def __init__(self, root: Path):
        self.path = root / "state" / "job-scan-seen.json"
        self.data = _read(self.path, {})

    def __contains__(self, key: str) -> bool:
        return key in self.data

    def add(self, key: str, title: str, company: str) -> None:
        self.data[key] = {
            "title": title,
            "company": company,
            "first_seen": date.today().isoformat(),
        }

    def save(self) -> None:
        _write(self.path, self.data)


class Budget:
    """Monthly request counter for quota-limited APIs."""

    def __init__(self, root: Path, limits: dict):
        self.path = root / "state" / "job-scan-budget.json"
        self.limits = limits or {}
        self.data = _read(self.path, {})
        self.month = date.today().strftime("%Y-%m")
        self.data.setdefault(self.month, {})

    def remaining(self, source: str) -> int:
        limit = self.limits.get(source)
        if limit is None:
            return 10**6
        return max(0, limit - self.data[self.month].get(source, 0))

    def spend(self, source: str, n: int = 1) -> None:
        self.data[self.month][source] = self.data[self.month].get(source, 0) + n

    def save(self) -> None:
        for month in list(self.data):  # keep the file small: 12 months is plenty
            if month < (date.today().replace(day=1).isoformat()[:7]) and len(self.data) > 12:
                self.data.pop(month)
        _write(self.path, self.data)


class Journal:
    """Append-only delivery journal. A run left in `sending` is never retried
    automatically: the outcome is unknown and a human must look."""

    STATES = ("prepared", "sending", "sent", "completed", "skipped", "failed")

    def __init__(self, root: Path):
        self.path = root / "state" / "job-scan-delivery.json"
        self.data = _read(self.path, {"runs": []})

    def has_open_send(self) -> bool:
        return any(r.get("state") == "sending" for r in self.data["runs"])

    def record(self, run_id: str, state: str, **extra) -> None:
        if state not in self.STATES:
            raise ValueError(f"unknown journal state: {state}")
        self.data["runs"].append(
            {
                "run_id": run_id,
                "state": state,
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                **extra,
            }
        )
        self.data["runs"] = self.data["runs"][-200:]

    def save(self) -> None:
        _write(self.path, self.data)
