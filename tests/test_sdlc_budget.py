from datetime import datetime, timedelta, timezone

from jobscan.sdlc import budget

NOW = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def run(id_, start_ago, minutes, status="completed", conclusion="success"):
    """A run that started `start_ago` before NOW and lasted `minutes` (or is still going)."""
    start = NOW - start_ago
    end = start + timedelta(minutes=minutes)
    return {"id": id_, "status": status, "conclusion": conclusion, "run_started_at": iso(start),
            "updated_at": iso(end), "created_at": iso(start)}


def used(runs, current=0, c24=1000, c7=1000):
    return budget.evaluate(runs, current, NOW, c24, c7)


def test_window_boundaries_clip_runs_to_the_window():
    inside = run(1, timedelta(hours=2), 10)
    straddles_24h = run(2, timedelta(hours=24, minutes=5), 10)      # 5 of its 10 minutes are inside 24h
    outside_24h = run(3, timedelta(hours=25), 10)
    straddles_7d = run(4, timedelta(days=7, minutes=4), 10)
    outside_7d = run(5, timedelta(days=8), 10)
    r = used([inside, straddles_24h, outside_24h, straddles_7d, outside_7d])
    assert r["used_24h"] == 15.0
    assert r["used_7d"] == 10 + 10 + 10 + 6.0


def test_a_run_shorter_than_30_seconds_is_ignored_and_30_seconds_counts():
    base = run(1, timedelta(hours=1), 0)
    def of(seconds):
        r = dict(base)
        r["updated_at"] = iso(NOW - timedelta(hours=1) + timedelta(seconds=seconds))
        return r
    assert used([of(29)])["used_24h"] == 0
    assert used([of(30)])["used_24h"] == 0.5


def test_current_and_cancelled_runs_are_excluded():
    runs = [run(1, timedelta(hours=1), 10), run(99, timedelta(hours=2), 10),
            run(3, timedelta(hours=3), 10, conclusion="cancelled")]
    assert used(runs, current=99)["used_24h"] == 10.0
    assert used(runs, current="99")["used_24h"] == 10.0


def test_a_run_in_progress_counts_up_to_now():
    r = run(1, timedelta(minutes=20), 999, status="in_progress", conclusion=None)   # updated_at is in the future
    assert used([r])["used_24h"] == 20.0
    queued = {"id": 2, "status": "queued", "conclusion": None, "run_started_at": None, "updated_at": iso(NOW)}
    assert used([queued])["used_24h"] == 0


def test_exactly_at_the_cap_is_allowed_and_one_minute_over_is_blocked():
    runs = [run(1, timedelta(hours=3), 60)]
    assert budget.evaluate(runs, 0, NOW, 60, 240)["allowed"] is True
    assert budget.evaluate(runs, 0, NOW, 59, 240)["allowed"] is False
    assert budget.evaluate(runs, 0, NOW, 60, 59)["allowed"] is False
    over = [run(1, timedelta(hours=3), 61)]
    r = budget.evaluate(over, 0, NOW, 60, 240)
    assert r["allowed"] is False and r["retry_after"] is not None and r["retry_after"] > NOW


def test_retry_time_is_when_usage_has_slid_back_under_the_cap():
    runs = [run(1, timedelta(hours=23), 120)]       # 120 minutes, all inside 24h, cap 60
    r = budget.evaluate(runs, 0, NOW, 60, 1000)
    # the run began 23h ago; 60 of its minutes must age out, i.e. until it is 60 minutes into the past 24h edge
    assert r["retry_after"] == NOW + timedelta(hours=1) + timedelta(minutes=60)


def test_cap_zero_blocks_everything_even_with_no_runs():
    assert budget.evaluate([], 0, NOW, 0, 240)["allowed"] is False
    assert budget.evaluate([], 0, NOW, 60, 0)["allowed"] is False
    assert budget.evaluate([], 0, NOW, 0, 0)["retry_after"] is None
    assert budget.evaluate([], 0, NOW, 60, 240)["allowed"] is True


def test_garbage_cap_values_fall_back_to_the_defaults():
    for bad in (None, "", " ", "abc", "-5", "1.5", "1e3", "∞", "unlimited", "٣"):
        assert budget.parse_cap(bad, 60) == 60
    assert budget.parse_cap("0", 60) == 0
    assert budget.parse_cap(" 90 ", 60) == 90
    assert (budget.DEFAULT_CAP_24H, budget.DEFAULT_CAP_7D) == (60, 240)


def test_pagination_stops_once_a_page_reaches_back_past_7_days():
    calls = []
    fresh = [run(i, timedelta(hours=1), 1) for i in range(100)]
    old = [run(1000 + i, timedelta(days=8), 1) for i in range(100)]
    pages = {1: fresh, 2: old, 3: fresh}

    def fetch(page, per_page, since):
        calls.append((page, per_page, since))
        return pages[page]

    runs = budget.collect_runs(fetch, NOW)
    assert [c[0] for c in calls] == [1, 2] and len(runs) == 200
    assert calls[0][1:] == (100, "2026-10-18")


def test_pagination_stops_on_a_short_page():
    calls = []

    def fetch(page, per_page, since):
        calls.append(page)
        return [run(1, timedelta(hours=1), 1)]

    assert len(budget.collect_runs(fetch, NOW)) == 1 and calls == [1]


def test_comment_and_summary_wording():
    r = budget.evaluate([run(1, timedelta(hours=3), 61)], 0, NOW, 60, 240)
    text = budget.render_comment(r)
    assert text.startswith("@RASMiranda: Budget gate: used 61.0 of 60 agent-minutes in the last 24h (61.0 of 240 in 7d). "
                           "Nothing ran. Try again after 2026-")
    s = budget.render_summary("build", r)
    assert "`build`" in s and "61.0 of 60" in s and "blocked" in s
    assert "the cap is raised" in budget.render_comment(budget.evaluate([], 0, NOW, 0, 240))
