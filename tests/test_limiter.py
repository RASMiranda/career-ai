"""Adaptive limiter on a fake clock: no real sleeping, every wait is recorded."""

from email.utils import formatdate

from jobscan.http.limiter import AdaptiveLimiter

WALL = 172800.0                    # a fixed wall clock for HTTP-date Retry-After values


class FakeTime:
    def __init__(self, start: float = 1000.0):
        self.now = start
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def limiter(self) -> AdaptiveLimiter:
        return AdaptiveLimiter(clock=self.clock, sleep=self.sleep, wall=lambda: WALL)


def test_starts_at_one_request_every_two_seconds():
    t = FakeTime()
    lim = t.limiter()
    assert lim.interval == 2.0
    assert lim.wait() == 0.0                       # the first request never waits
    assert t.slept == []


def test_no_sleep_once_two_seconds_have_passed_and_a_short_sleep_otherwise():
    t = FakeTime()
    lim = t.limiter()
    lim.wait()
    t.advance(2.0)
    assert lim.wait() == 0.0 and t.slept == []     # exactly 2 s apart: no sleep
    t.advance(0.5)
    assert lim.wait() == 1.5 and t.slept == [1.5]  # 0.5 s apart: sleeps the remaining 1.5 s


def test_the_second_429_switches_to_ten_seconds_and_not_before():
    t = FakeTime()
    lim = t.limiter()
    lim.wait()
    lim.on_response(429)
    assert lim.throttled == 1 and lim.interval == 2.0          # the first 429 does not switch
    lim.wait()
    assert t.slept == [2.0]
    lim.on_response(429)
    assert lim.throttled == 2 and lim.interval == 10.0         # exactly the second one does
    lim.wait()
    assert t.slept == [2.0, 10.0]                              # the next request waits the new interval


def test_other_statuses_do_not_count_as_throttling():
    t = FakeTime()
    lim = t.limiter()
    for status in (200, 404, 500, 503):
        lim.on_response(status)
    assert lim.throttled == 0 and lim.interval == 2.0


def test_retry_after_seconds_is_honoured_on_429_and_503():
    for status in (429, 503):
        t = FakeTime()
        lim = t.limiter()
        lim.wait()
        lim.on_response(status, "30")
        lim.wait()
        assert t.slept == [30.0], status


def test_retry_after_http_date_is_honoured():
    t = FakeTime()
    lim = t.limiter()
    lim.wait()
    lim.on_response(429, formatdate(WALL + 10, usegmt=True))   # ten seconds from the wall clock
    lim.wait()
    assert t.slept == [10.0]


def test_a_garbage_or_missing_retry_after_is_ignored():
    for value in ("soon", "-5", "", None):
        t = FakeTime()
        lim = t.limiter()
        lim.wait()
        lim.on_response(429, value)
        assert lim.wait() == 2.0 and t.slept == [2.0], value   # only the normal interval applies


def test_state_is_per_instance_so_each_run_starts_fresh():
    t = FakeTime()
    old = t.limiter()
    old.wait()
    old.on_response(429)
    old.wait()
    old.on_response(429)
    assert old.interval == 10.0

    new = t.limiter()
    assert new.interval == 2.0 and new.throttled == 0
    new.wait()                                    # a new run's first request does not wait on the old run
    assert t.slept == [2.0]                       # only the old run's own wait was recorded
