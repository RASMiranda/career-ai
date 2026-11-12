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


def test_csv_and_jsonl_vocabularies_agree_where_they_overlap():
    from jobscan import bank
    assert set(applylog.STATUSES) <= set(bank.STATUSES)
    assert set(bank.STATUSES) == set(applylog.APPLY_STATUSES)
    assert set(applylog.APPLY_STATUSES) - set(applylog.STATUSES) == {"STAGED", "CLOSED"}
    assert set(applylog.APPLIED) <= set(applylog.STATUSES)


def test_already_applied_is_valid_in_the_csv(log):
    assert add(log, status="ALREADY_APPLIED")["status"] == "ALREADY_APPLIED"
    assert applylog.read(log)[0]["status"] == "ALREADY_APPLIED"
    for bad in ("STAGED", "CLOSED"):
        with pytest.raises(applylog.ApplyLogError):
            add(log, job_id="2", status=bad)


# ---- CLI: upsert / outcome / check (ADR-050) ----

import json

HEADER = "date,site,employer,role,job_id,status"


def run(*argv):
    return applylog.main(list(argv))


def up(path, **kw):
    base = dict(date="2026-11-12", site="example", employer="Example", role="Engineer", job_id="abc",
                status="SUBMITTED")
    base.update(kw)
    args = ["upsert", "--log", str(path)]
    for k, v in base.items():
        args += ["--" + k.replace("_", "-"), v]
    return run(*args)


def test_upsert_appends_and_keeps_header_and_comments_byte_identical(tmp_path):
    p = tmp_path / "log.csv"
    original = f"# TODO note\n{HEADER}\n# another comment\n2026-11-01,example,Acme,Dev,1,SKIPPED\n"
    p.write_bytes(original.encode())
    assert up(p) == 0
    text = p.read_bytes().decode()
    assert text.startswith(original)
    assert text.endswith("2026-11-12,example,Example,Engineer,abc,SUBMITTED\n")
    assert len(text.splitlines()) == len(original.splitlines()) + 1


def test_upsert_replaces_exactly_that_line_and_keeps_crlf(tmp_path):
    p = tmp_path / "log.csv"
    lines = [HEADER, "# c", "2026-11-01,example,Acme,Dev,1,CANDIDATE", "2026-11-02,example,Other,Dev,abc,CANDIDATE",
             "2026-11-03,other,Z,Dev,abc,SKIPPED"]
    p.write_bytes(("\r\n".join(lines) + "\r\n").encode())
    assert up(p) == 0
    out = p.read_bytes().decode().split("\r\n")
    assert out[:3] == lines[:3] and out[4] == lines[4]
    assert out[3] == "2026-11-12,example,Example,Engineer,abc,SUBMITTED"
    assert len(out) == len(lines) + 1  # trailing empty piece
    assert "\r\n" in p.read_bytes().decode() and "\n" not in p.read_bytes().decode().replace("\r\n", "")


def test_upsert_quotes_commas_and_read_returns_them_intact(tmp_path):
    p = tmp_path / "log.csv"
    assert up(p, role="Engineer, Java") == 0
    assert up(p, role="Engineer, Java") == 0
    assert '"Engineer, Java"' in p.read_text()
    rows = applylog.read(p)
    assert len(rows) == 1 and rows[0]["role"] == "Engineer, Java"


def test_check_reports_pipe_row_number(tmp_path, capsys):
    p = tmp_path / "log.csv"
    p.write_text(f"{HEADER}\n2026-11-01,example,Acme,Dev,1,SKIPPED\n2026-11-12 | example | Acme | Dev | 2 | SUBMITTED\n")
    assert run("check", "--log", str(p)) == 2
    assert "row 2" in capsys.readouterr().err


def test_check_ok(tmp_path, capsys):
    p = tmp_path / "log.csv"
    up(p)
    capsys.readouterr()
    assert run("check", "--log", str(p)) == 0
    assert "ok, 1 rows" in capsys.readouterr().out


@pytest.mark.parametrize("kw", [{"status": "DONE"}, {"date": "12/11/2026"}, {"site": "SmartRecruiters"}])
def test_upsert_invalid_exits_2_and_leaves_file_unchanged(tmp_path, kw):
    p = tmp_path / "log.csv"
    up(p, job_id="keep")
    before = p.read_bytes()
    assert up(p, **kw) == 2
    assert p.read_bytes() == before


def test_upsert_invalid_does_not_create_file(tmp_path):
    p = tmp_path / "log.csv"
    assert up(p, status="DONE") == 2
    assert not p.exists()


def test_outcome_writes_redacted_jsonl_line(tmp_path):
    assert run("outcome", "--data", str(tmp_path), "--site", "example", "--job-id", "abc", "--employer", "Example",
               "--role", "see https://example.com/ok?token=SECRET#f", "--status", "SUBMITTED",
               "--ts", "2026-11-12", "--verified-by", "confirmation_url") == 0
    f = tmp_path / "logs" / "apply" / "example-2026-11-12.jsonl"
    lines = f.read_text().splitlines()
    assert len(lines) == 1
    d = json.loads(lines[0])
    assert d["verified_by"] == "confirmation_url" and "SECRET" not in lines[0] and d["role"].endswith("/ok")


def test_outcome_unknown_verifier_exits_2(tmp_path):
    with pytest.raises(SystemExit) as e:
        run("outcome", "--data", str(tmp_path), "--site", "example", "--job-id", "abc", "--employer", "E",
            "--role", "R", "--status", "SUBMITTED", "--ts", "2026-11-12", "--verified-by", "foo")
    assert e.value.code == 2
    assert not (tmp_path / "logs").exists()
