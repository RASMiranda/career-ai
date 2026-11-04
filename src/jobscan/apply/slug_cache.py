"""Greenhouse job id -> board slug and host, learned only from a form page that answered HTTP 200.

Rules, in code and not only in prose:
- A slug is written only after the form page for that slug returned HTTP 200 (``record``/``verify``).
- A miss is NOT_FOUND. ``locate`` never guesses a slug and never touches the network; the caller marks
  the job NOT_FOUND.
- No function here derives a slug from a job id. ``get`` returns what was verified, or None.

File: ``state/slug_cache.json`` in the data repo, shaped ``{job_id: {slug, host, verified_at}}``.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from ..store import Store
from .adapters import ApplyFailure, Code
from .greenhouse import GreenhouseRef

FILE = "state/slug_cache.json"


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class SlugCache:
    def __init__(self, store: Store, now: Callable[[], str] = utc_now):
        self.store = store
        self.now = now
        self.items: dict = store.read_json(FILE, {}) or {}

    def get(self, job_id: str) -> dict | None:
        """The verified entry for this job id, or None. A miss is never filled in by inference."""
        entry = self.items.get(job_id)
        return dict(entry) if entry else None

    def record(self, ref: GreenhouseRef, status: int) -> bool:
        """Remember ``ref`` only if its form page answered HTTP 200. Any other status writes nothing."""
        if status != 200:
            return False
        self.items[ref.job_id] = {"slug": ref.slug, "host": ref.host, "verified_at": self.now()}
        self.store.write_json(FILE, self.items)
        return True


def verify(ref: GreenhouseRef, cache: SlugCache, status_of: Callable[[str], int]) -> bool:
    """Check the form page for ``ref`` through the injected ``status_of(url) -> HTTP status``, then record it."""
    return cache.record(ref, status_of(ref.form_url()))


def locate(job_id: str, cache: SlugCache) -> GreenhouseRef:
    """The reference for a job id verified before. A miss raises ApplyFailure NOT_FOUND, with no guess."""
    hit = cache.get(job_id)
    if hit is None:
        raise ApplyFailure(Code.NOT_FOUND, "job id has no verified board slug", "locate")
    return GreenhouseRef(hit["slug"], job_id, hit["host"])
