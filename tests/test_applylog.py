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


# ---- batch / check hardening (ADR-053). Fake employers, fake job IDs; no ID-shaped literals ----

BATCH_HEADER = "date,site,employer,role,job_id,status,verified_by,ts"
ROW_A = "2026-11-11,greenhouse,Acme Labs,Software Engineer,1000001,SUBMITTED,confirmation_url,2026-11-11"
ROW_B = "2026-11-12,greenhouse,Beta Works,Tech Lead,1000002,BLOCKED,,2026-11-12"
# Built at run time so the test file never holds a formatted CPF.
FAKE_CPF = "-".join([".".join(["111", "222", "333"]), "44"])
FAKE_DOC_DIGITS = "1" * 11


def make_data(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    return data


def write_rows(path, *lines):
    path.write_text("\n".join([BATCH_HEADER, *lines]) + "\n", encoding="utf-8")


def batch(data, rows, capsys=None):
    return run("batch", "--log", str(data / "apply" / "log.csv"), "--data", str(data), "--file", str(rows))


def test_batch_writes_log_rows_and_jsonl_outcomes(tmp_path, capsys):
    data = make_data(tmp_path)
    rows = tmp_path / "rows.csv"
    write_rows(rows, ROW_A, ROW_B)
    assert batch(data, rows) == 0
    out = capsys.readouterr().out
    assert "2 new, 0 updated, 0 unchanged" in out
    log = (data / "apply" / "log.csv").read_text(encoding="utf-8").splitlines()
    assert log[0] == "date,site,employer,role,job_id,status"
    assert log[1] == "2026-11-11,greenhouse,Acme Labs,Software Engineer,1000001,SUBMITTED"
    assert log[2] == "2026-11-12,greenhouse,Beta Works,Tech Lead,1000002,BLOCKED"
    recs = [json.loads(x) for x in (data / "logs" / "apply" / "greenhouse-2026-11-11.jsonl").read_text().splitlines()]
    assert recs == [{"employer": "Acme Labs", "job_id": "1000001", "role": "Software Engineer",
                     "site": "greenhouse", "status": "SUBMITTED", "ts": "2026-11-11",
                     "verified_by": "confirmation_url"}]
    # BLOCKED with no verifier writes no outcome
    assert not (data / "logs" / "apply" / "greenhouse-2026-11-12.jsonl").exists()


def test_batch_is_all_or_nothing_on_one_bad_row(tmp_path, capsys):
    data = make_data(tmp_path)
    rows = tmp_path / "rows.csv"
    bad = "2026-11-12,greenhouse,Beta Works,Tech Lead,1000002,SUBMITTED,,2026-11-12"  # SUBMITTED, no verifier
    write_rows(rows, ROW_A, bad)
    assert batch(data, rows) == 2
    assert "error: row 2:" in capsys.readouterr().err
    assert not (data / "apply" / "log.csv").exists()
    assert not (data / "logs").exists()


def test_batch_second_run_changes_nothing(tmp_path, capsys):
    data = make_data(tmp_path)
    rows = tmp_path / "rows.csv"
    write_rows(rows, ROW_A, ROW_B)
    assert batch(data, rows) == 0
    log_before = (data / "apply" / "log.csv").read_bytes()
    jsonl = data / "logs" / "apply" / "greenhouse-2026-11-11.jsonl"
    jsonl_before = jsonl.read_bytes()
    capsys.readouterr()
    assert batch(data, rows) == 0
    out = capsys.readouterr().out
    assert "0 new, 0 updated, 2 unchanged" in out
    assert "outcomes: 0 written" in out
    assert (data / "apply" / "log.csv").read_bytes() == log_before
    assert jsonl.read_bytes() == jsonl_before


def test_batch_updates_an_existing_row_in_place(tmp_path, capsys):
    data = make_data(tmp_path)
    rows = tmp_path / "rows.csv"
    write_rows(rows, ROW_B)
    batch(data, rows)
    write_rows(rows, ROW_B.replace("BLOCKED,,", "UNCONFIRMED,gmail,"))
    capsys.readouterr()
    assert batch(data, rows) == 0
    assert "0 new, 1 updated, 0 unchanged" in capsys.readouterr().out


@pytest.mark.parametrize("row, reason", [
    ("2026-11-12,greenhouse,Beta Works,Tech Lead,1000002,ALREADY_APPLIED,confirmation_url,2026-11-12",
     "must be verified by site_applied_list or human"),
    ("2026-11-12,greenhouse,Beta Works,Tech Lead,1000002,ALREADY_APPLIED,,2026-11-12",
     "must be verified by site_applied_list or human"),
    ("2026-11-12,greenhouse,Beta Works,Tech Lead,1000002,DONE,,2026-11-12", "unknown status"),
])
def test_batch_rejects_already_applied_without_a_site_or_human_verifier(tmp_path, capsys, row, reason):
    data = make_data(tmp_path)
    rows = tmp_path / "rows.csv"
    write_rows(rows, ROW_A, row)
    assert batch(data, rows) == 2
    err = capsys.readouterr().err
    assert "error: row 2:" in err and reason in err
    assert not (data / "apply" / "log.csv").exists()


def test_batch_refuses_a_duplicate_site_and_job_id_inside_the_file(tmp_path, capsys):
    data = make_data(tmp_path)
    rows = tmp_path / "rows.csv"
    write_rows(rows, ROW_A, ROW_A)
    assert batch(data, rows) == 2
    assert "error: row 2:" in capsys.readouterr().err


def test_batch_refuses_an_id_number_in_a_field(tmp_path, capsys):
    data = make_data(tmp_path)
    rows = tmp_path / "rows.csv"
    write_rows(rows, ROW_A.replace("Software Engineer", f"documento {FAKE_DOC_DIGITS}"))
    assert batch(data, rows) == 2
    err = capsys.readouterr().err
    assert "government ID number" in err
    assert FAKE_DOC_DIGITS not in err
    assert not (data / "apply" / "log.csv").exists()


def test_check_rejects_a_formatted_cpf_without_echoing_it(tmp_path, capsys):
    log = tmp_path / "log.csv"
    log.write_text(f"{HEADER}\n2026-11-11,example,Acme,Dev {FAKE_CPF},1000001,SKIPPED\n", encoding="utf-8")
    assert run("check", "--log", str(log)) == 2
    err = capsys.readouterr().err
    assert f"{log}:2:" in err
    assert FAKE_CPF not in err and "111" not in err


def test_check_rejects_a_documento_label_and_its_jsonl_twin(tmp_path, capsys):
    log = tmp_path / "log.csv"
    log.write_text(f"{HEADER}\n2026-11-11,example,Acme,documento {FAKE_DOC_DIGITS},1000001,SKIPPED\n",
                   encoding="utf-8")
    assert run("check", "--log", str(log)) == 2
    assert FAKE_DOC_DIGITS not in capsys.readouterr().err

    data = tmp_path / "data"
    (data / "logs" / "apply").mkdir(parents=True)
    jl = data / "logs" / "apply" / "example-2026-11-11.jsonl"
    jl.write_text(json.dumps({"job_id": "1", "role": f"passport {FAKE_DOC_DIGITS}", "site": "example",
                              "status": "SKIPPED", "ts": "2026-11-11", "verified_by": "",
                              "employer": "Acme"}) + "\n", encoding="utf-8")
    assert run("check", "--log", str(log), "--data", str(data)) == 2
    err = capsys.readouterr().err
    assert str(jl) in err and FAKE_DOC_DIGITS not in err


def test_check_warns_on_a_submitted_row_without_an_outcome_and_strict_fails(tmp_path, capsys):
    data = make_data(tmp_path)
    (data / "apply").mkdir()
    log = data / "apply" / "log.csv"
    log.write_text(f"{HEADER}\n2026-11-11,greenhouse,Acme Labs,Dev,1000001,SUBMITTED\n", encoding="utf-8")
    capsys.readouterr()
    assert run("check", "--log", str(log), "--data", str(data)) == 0
    assert "warning: no outcome for greenhouse 1000001" in capsys.readouterr().out
    assert run("check", "--log", str(log), "--data", str(data), "--strict") == 2
    # once the outcome exists, the warning goes away
    assert run("outcome", "--data", str(data), "--site", "greenhouse", "--job-id", "1000001",
               "--employer", "Acme Labs", "--role", "Dev", "--status", "SUBMITTED",
               "--ts", "2026-11-11", "--verified-by", "confirmation_url") == 0
    capsys.readouterr()
    assert run("check", "--log", str(log), "--data", str(data), "--strict") == 0
    assert "warning" not in capsys.readouterr().out


def test_batch_keeps_comments_and_unrelated_lines_byte_identical(tmp_path, capsys):
    data = make_data(tmp_path)
    (data / "apply").mkdir()
    log = data / "apply" / "log.csv"
    original = (f"# TODO-RUI: batch 1 rows are elsewhere\n{HEADER}\n# another note\n"
                "2026-11-01,example,Acme,Dev,1,SKIPPED\n"
                "2026-11-02,greenhouse,Acme Labs,Dev,1000001,CANDIDATE\n"
                "# trailing note\n")
    log.write_bytes(original.encode())
    rows = tmp_path / "rows.csv"
    write_rows(rows, ROW_A)  # updates the CANDIDATE line in place
    assert batch(data, rows) == 0
    text = log.read_text(encoding="utf-8")
    assert text.splitlines() == [
        "# TODO-RUI: batch 1 rows are elsewhere",
        HEADER,
        "# another note",
        "2026-11-01,example,Acme,Dev,1,SKIPPED",
        "2026-11-11,greenhouse,Acme Labs,Software Engineer,1000001,SUBMITTED",
        "# trailing note",
    ]
