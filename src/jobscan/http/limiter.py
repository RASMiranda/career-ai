"""Adaptive request spacing for one run.

Starts at one request per 2 seconds. After the second HTTP 429 in the same run it drops to one request per
10 seconds for the rest of that run. A Retry-After header on a 429 or 503 is honoured as a minimum wait
before the next request.

State lives on the instance, so each run makes its own limiter (no module globals). The clock, the sleep
and the wall clock (for HTTP-date Retry-After values) are injected, so tests run on a fake clock.
"""

import re
import time
from collections.abc import Callable
from datetime import UTC
from email.utils import parsedate_to_datetime

START_INTERVAL = 2.0          # seconds between requests at the start of a run
SLOW_INTERVAL = 10.0          # seconds between requests after the run has been throttled twice
SLOW_AFTER_429S = 2           # the second 429 in a run switches to the slow interval
_SECONDS = re.compile(r"[0-9]+")


class AdaptiveLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 wall: Callable[[], float] = time.time):
        self._clock, self._sleep, self._wall = clock, sleep, wall
        self.interval = START_INTERVAL
        self.throttled = 0                 # 429 responses seen in this run
        self._last: float | None = None    # when the previous request started
        self._hold_until: float | None = None   # Retry-After: nothing before this moment

    def wait(self) -> float:
        """Block until the next request may start. Returns the seconds slept (0.0 if none)."""
        now = self._clock()
        target = now
        if self._last is not None:
            target = max(target, self._last + self.interval)
        if self._hold_until is not None:
            target = max(target, self._hold_until)
        slept = max(0.0, target - now)
        if slept > 0:
            self._sleep(slept)
        self._last = self._clock()
        return slept

    def on_response(self, status: int, retry_after: str | None = None) -> None:
        """Feed each response back in; a 429 may slow the rest of the run."""
        if status == 429:
            self.throttled += 1
            if self.throttled >= SLOW_AFTER_429S:
                self.interval = SLOW_INTERVAL
        if status in (429, 503) and retry_after:
            seconds = self._retry_seconds(retry_after)
            if seconds is not None:
                self._hold_until = self._clock() + seconds

    def _retry_seconds(self, value: str) -> float | None:
        value = value.strip()
        if _SECONDS.fullmatch(value):
            return float(value)
        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return max(0.0, when.timestamp() - self._wall())
