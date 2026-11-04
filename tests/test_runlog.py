"""Run log: one appended line per run, counts that add up, nothing rewritten."""

from jobscan.apply.adapters import Code
from jobscan.apply.runlog import COUNTERS, FILE, RunLog, counter_for, site_of
from jobscan.store import FileStore

URL = "https://jobs.lever.co/acme/1"


def fixed_now():
    return "2026-11-04T10:00:00+00:00"


def test_each_outcome_adds_to_exactly_one_counter(tmp_path):
    table = [
        ("submitted", "submitted_count"),
        (Code.CONSENT_PENDING, "consent_pending_count"),
        (Code.NOT_FOUND, "not_found_count"),
        (Code.UNKNOWN_REQUIRED_FIELD, "skipped_count"),
        ("filled_not_submitted", "skipped_count"),
        ("already_applied", "skipped_count"),
        (Code.CAPTCHA, "skipped_count"),
    ]
    log = RunLog(FileStore(tmp_path), now=fixed_now)
    for outcome, counter in table:
        assert counter_for(outcome) == counter, outcome
        row = log.finish(log.start("r1", URL), outcome)
        assert row[counter] == 1 and sum(row[c] for c in COUNTERS) == 1, outcome


def test_a_line_carries_the_site_the_run_started_from(tmp_path):
    log = RunLog(FileStore(tmp_path), now=fixed_now)
    row = log.finish(log.start("abcd1234", URL), "submitted")
    assert row == {"run_id": "abcd1234", "site": "jobs.lever.co", "source_url": URL,
                   "started_at": fixed_now(), "ended_at": fixed_now(),
                   "submitted_count": 1, "skipped_count": 0, "consent_pending_count": 0,
                   "not_found_count": 0}
    assert FileStore(tmp_path).read_lines(FILE) == [row]


def test_lines_are_appended_and_earlier_ones_are_never_rewritten(tmp_path):
    store = FileStore(tmp_path)
    log = RunLog(store, now=fixed_now)
    log.finish(log.start("r1", URL), "submitted")
    before = (tmp_path / FILE).read_bytes()
    log.finish(log.start("r2", URL), Code.NOT_FOUND)
    after = (tmp_path / FILE).read_bytes()
    assert after.startswith(before) and len(after) > len(before)
    assert [row["run_id"] for row in store.read_lines(FILE)] == ["r1", "r2"]


def test_site_of_reads_the_host_and_tolerates_junk():
    assert site_of("https://JOBS.lever.co/acme/1") == "jobs.lever.co"
    assert site_of("not a url") == ""
    assert site_of("") == ""
