"""One line per application run in ``logs/runs.jsonl``, appended through the Store.

A run here is one job's pass through the apply runner: the site it went to, the posting link it started
from, and how it ended. Each line carries 0 or 1 in each counter; a day's totals are the sums. Lines are
appended and never rewritten.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlparse

from ..store import Store
from .adapters import Code

FILE = "logs/runs.jsonl"     # not under logs/apply/: that folder holds failure lines with "at"
COUNTERS = ("submitted_count", "skipped_count", "consent_pending_count", "not_found_count")


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def site_of(url: str) -> str:
    try:
        return (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""


def counter_for(outcome: str) -> str:
    """Which counter one outcome adds to. Anything that did not submit and is not a consent or a
    missing address is a skip: it was looked at, and the owner does it by hand."""
    return {"submitted": "submitted_count",
            Code.CONSENT_PENDING: "consent_pending_count",
            Code.NOT_FOUND: "not_found_count"}.get(outcome, "skipped_count")


class RunLog:
    def __init__(self, store: Store, now: Callable[[], str] = utc_now):
        self.store = store
        self.now = now

    def start(self, run_id: str, source_url: str) -> dict:
        return {"run_id": run_id, "site": site_of(source_url), "source_url": source_url,
                "started_at": self.now(), **{name: 0 for name in COUNTERS}}

    def finish(self, run: dict, outcome: str) -> dict:
        """Count the outcome against this run and append the finished line."""
        row = {**run, "ended_at": self.now()}
        counter = counter_for(outcome)
        row[counter] = row.get(counter, 0) + 1
        self.store.append_line(FILE, row)
        return row
