from datetime import date

import pytest

from jobscan import applylog


@pytest.fixture
def log(tmp_path):
    return tmp_path / "apply" / "log.csv"


def add(log, **kw):
    base = {"site": "glassdoor", "employer": "Acme", "role": "Dev", "job_id": "1", "status": "CANDIDATE",
            "when": "2026-06-01"}
    base.update(kw)
    return applylog.append(log, **base)


def test_missing_file_is_empty_and_append_writes_header(log):
    assert applylog.read(log) == []
    add(log, job_id="42", status="SUBMITTED")
    assert log.read_text(encoding="utf-8").splitlines()[0] == "date,site,employer,role,job_id,status"
    assert applylog.read(log) == [{"date": "2026-06-01", "site": "glassdoor", "employer": "Acme",
                                   "role": "Dev", "job_id": "42", "status": "SUBMITTED"}]


def test_comment_lines_are_kept_but_not_read(log):
    log.parent.mkdir(parents=True)
    log.write_text("# TODO-RUI: batch 1 rows are elsewhere\n"
                   "date,site,employer,role,job_id,status\n"
                   "# another note\n"
                   "2026-06-01,glassdoor,Acme,Dev,7,SKIPPED\n", encoding="utf-8")
    add(log, job_id="8", status="BLOCKED")
    text = log.read_text(encoding="utf-8")
    assert text.startswith("# TODO-RUI")
    assert [r["job_id"] for r in applylog.read(log)] == ["7", "8"]


def test_appends_after_a_file_with_no_trailing_newline(log):
    log.parent.mkdir(parents=True)
    log.write_text("date,site,employer,role,job_id,status\n2026-06-01,glassdoor,Acme,Dev,7,SKIPPED",
                   encoding="utf-8")
    add(log, job_id="8")
    assert [r["job_id"] for r in applylog.read(log)] == ["7", "8"]


def test_rejects_unknown_status_and_bad_header(log, tmp_path):
    with pytest.raises(applylog.ApplyLogError):
        add(log, status="DONE")
    bad = tmp_path / "bad.csv"
    bad.write_text("when,site,job\n", encoding="utf-8")
    with pytest.raises(applylog.ApplyLogError):
        applylog.read(bad)


def test_rejects_unknown_status_on_read(tmp_path):
    p = tmp_path / "log.csv"
    p.write_text("date,site,employer,role,job_id,status\n2026-06-01,x,Acme,Dev,1,WHATEVER\n",
                 encoding="utf-8")
    with pytest.raises(applylog.ApplyLogError):
        applylog.read(p)


def test_is_duplicate_matches_site_and_job_id_whatever_the_status(log):
    add(log, site="glassdoor", job_id="1010295439487", status="SKIPPED")
    assert applylog.is_duplicate(log, "glassdoor", "1010295439487")
    assert applylog.is_duplicate(log, " Glassdoor ", "1010295439487")
    assert not applylog.is_duplicate(log, "linkedin", "1010295439487")
    assert not applylog.is_duplicate(log, "glassdoor", "1010295439488")


def test_employer_applied_recently_counts_only_applied_statuses_inside_the_window(log):
    today = date(2026, 11, 5)
    add(log, employer="Agoda Co.", when="2026-06-01", status="SUBMITTED")   # 157 days: inside 180
    add(log, employer="Old Corp", when="2026-01-01", status="SUBMITTED")    # outside
    add(log, employer="Skipped Ltd", when="2026-10-01", status="SKIPPED")   # not applied
    add(log, employer="Candidate SA", when="2026-10-01", status="CANDIDATE")
    assert applylog.employer_applied_recently(log, "Agoda", today=today)    # canon ignores "Co."
    assert applylog.employer_applied_recently(log, "AGODA", today=today)
    assert not applylog.employer_applied_recently(log, "Old Corp", today=today)
    assert not applylog.employer_applied_recently(log, "Skipped Ltd", today=today)
    assert not applylog.employer_applied_recently(log, "Candidate SA", today=today)
    assert not applylog.employer_applied_recently(log, "Nobody", today=today)
    assert not applylog.employer_applied_recently(log, "", today=today)


def test_blank_date_counts_as_recent_so_an_employer_is_not_applied_to_twice(log):
    log.parent.mkdir(parents=True)
    log.write_text("date,site,employer,role,job_id,status\n,TODO,DMG,TODO,1010304969193,SUBMITTED\n",
                   encoding="utf-8")
    assert applylog.employer_applied_recently(log, "DMG", today=date(2030, 1, 1))


def test_window_edges_and_bad_dates(log):
    add(log, employer="Edge Co", when="2026-05-09", status="SUBMITTED")   # exactly 180 days before
    assert applylog.employer_applied_recently(log, "Edge Co", today=date(2026, 11, 5))
    with pytest.raises(applylog.ApplyLogError):
        add(log, employer="Bad Co", when="5 Nov 2026", status="SUBMITTED")
