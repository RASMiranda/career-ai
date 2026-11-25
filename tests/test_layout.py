"""Profile file layout (ADR-069, ADR-070, ADR-072): every profile file lives under profiles/<id>/, there is
no root-path fallback, and a command needs a profile id (explicit, or the only profile folder)."""

import hashlib
import os
import json
from pathlib import Path

import pytest

from jobscan import cvcheck, layout
from jobscan.cli import main
from jobscan.config import ConfigError


def touch(root: Path, rel: str, text: str = "x\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def profile(root: Path, pid: str) -> None:
    touch(root, f"profiles/{pid}/profile.yaml", "display_name: Synthetic\n")


def test_resolve_is_the_profile_folder_path_and_nothing_else(tmp_path):
    profile(tmp_path, "rui")
    expected = tmp_path / "profiles/rui/answer_bank.yaml"
    assert layout.resolve(tmp_path, "rui", "answer_bank.yaml") == expected
    assert layout.resolve(tmp_path, "rui", "apply/triage.yaml") == tmp_path / "profiles/rui/apply/triage.yaml"


def test_a_file_only_at_the_old_root_path_is_not_found(tmp_path):
    profile(tmp_path, "rui")
    touch(tmp_path, "apply/triage.yaml", "keywords\n")                 # the pre-ADR-070 location
    touch(tmp_path, "state/cv_manifest.json", "{}")
    assert layout.resolve(tmp_path, "rui", "apply/triage.yaml") == tmp_path / "profiles/rui/apply/triage.yaml"
    assert not layout.resolve(tmp_path, "rui", "apply/triage.yaml").exists()


def test_a_missing_cv_manifest_error_names_the_profile_path(tmp_path, capsys):
    profile(tmp_path, "rui")
    touch(tmp_path, "cv_manifest.json", json.dumps({"cv/general.md": hashlib.sha256(b"x").hexdigest()}))
    with pytest.raises(cvcheck.CvCheckError, match=r"profiles/rui/cv_manifest\.json"):
        cvcheck.check(tmp_path, "rui")                                  # the root copy is ignored
    assert main(["cv-check", "--data", str(tmp_path), "--profile", "rui"]) == 2
    assert "profiles/rui/cv_manifest.json" in capsys.readouterr().err


def test_no_profile_folder_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match=r"no profile: expected profiles/<id>/profile\.yaml"):
        layout.default_profile(tmp_path)
    touch(tmp_path, "profiles/notes/readme.md")                         # a folder without profile.yaml
    with pytest.raises(ConfigError, match="no profile"):
        layout.default_profile(tmp_path)


def test_several_profiles_without_an_explicit_id_is_a_config_error(tmp_path, capsys):
    profile(tmp_path, "ana")
    profile(tmp_path, "bruno")
    with pytest.raises(ConfigError, match="--profile"):
        layout.default_profile(tmp_path)
    assert layout.default_profile(tmp_path, "bruno") == "bruno"       # explicit always wins
    assert main(["cv-check", "--data", str(tmp_path)]) == 2
    assert "--profile" in capsys.readouterr().err


def test_one_profile_is_the_default(tmp_path):
    profile(tmp_path, "rui")
    touch(tmp_path, "profiles/notes/readme.md")                         # a folder without profile.yaml
    assert layout.default_profile(tmp_path) == "rui"


def test_resolve_requires_a_profile_id(tmp_path):
    with pytest.raises(ValueError, match="profile id"):
        layout.resolve(tmp_path, "", "answer_bank.yaml")


def test_names_outside_the_data_repo_are_refused(tmp_path):
    for bad in ("../answer_bank.yaml", "/etc/hosts", "", "apply/../../x"):
        with pytest.raises(ValueError):
            layout.resolve(tmp_path, "rui", bad)


def test_cv_check_reads_the_profile_manifest_with_keys_relative_to_the_profile(tmp_path, capsys):
    profile(tmp_path, "rui")
    data = b"General CV, synthetic\n"
    touch(tmp_path, "profiles/rui/cv/general.md", data.decode())
    manifest = {"cv/general.md": hashlib.sha256(data).hexdigest()}
    touch(tmp_path, "profiles/rui/cv_manifest.json", json.dumps(manifest))
    report = cvcheck.check(tmp_path, "rui")
    assert report.fresh and report.checked == 1
    assert main(["cv-check", "--data", str(tmp_path)]) == 0            # default profile, no flag
    assert "all 1 CV file(s)" in capsys.readouterr().out


def test_cv_check_keys_that_point_at_the_data_root_are_not_read(tmp_path):
    profile(tmp_path, "rui")
    data = b"CV card, synthetic\n"
    touch(tmp_path, "profiles/rui/cv/general.md", data.decode())
    manifest = {"profiles/rui/cv/general.md": hashlib.sha256(data).hexdigest()}
    touch(tmp_path, "profiles/rui/cv_manifest.json", json.dumps(manifest))
    report = cvcheck.check(tmp_path, "rui")
    assert report.missing == ["profiles/rui/cv/general.md"]            # keys resolve inside the profile only


# ---- ADR-071 phase B, ADR-072: apply-run records under profiles/<id>/, no root fallback ----

from jobscan import applylog, bank  # noqa: E402

LOG_ROW = "date,site,employer,role,job_id,status\n2026-06-01,glassdoor,Acme,Dev,42,CANDIDATE\n"


def test_apply_log_created_at_the_profile_path_when_it_exists_nowhere(tmp_path):
    profile(tmp_path, "rui")
    path = layout.resolve(tmp_path, "rui", "apply/log.csv")
    assert path == tmp_path / "profiles/rui/apply/log.csv"
    applylog.upsert(path, site="glassdoor", employer="Acme", role="Dev", job_id="1",
                    status="CANDIDATE", when="2026-06-01")
    assert path.is_file() and not (tmp_path / "apply/log.csv").exists()


def test_a_root_apply_log_is_not_found_when_a_profile_folder_exists(tmp_path):
    profile(tmp_path, "rui")
    touch(tmp_path, "apply/log.csv", LOG_ROW)                          # the pre-#65 location
    path = layout.resolve(tmp_path, "rui", "apply/log.csv")
    assert path == tmp_path / "profiles/rui/apply/log.csv"
    assert not path.exists()
    assert layout.apply_path(tmp_path, "apply/log.csv", "rui") == path
    assert applylog.read(path) == []                                   # the root row is not read


def test_apply_log_and_outcome_records_resolve_to_the_profile_path_even_with_root_copies(tmp_path):
    profile(tmp_path, "rui")
    touch(tmp_path, "apply/legacy-outcomes.csv", "site,job_id,reason\n")
    touch(tmp_path, "logs/apply/arc-2026-11-12.jsonl", "{}\n")
    assert layout.resolve(tmp_path, "rui", "apply/legacy-outcomes.csv") == \
        tmp_path / "profiles/rui/apply/legacy-outcomes.csv"
    assert layout.resolve(tmp_path, "rui", "logs/apply") == tmp_path / "profiles/rui/logs/apply"
    assert layout.apply_path(tmp_path, "logs/apply", "rui") == tmp_path / "profiles/rui/logs/apply"
    assert layout.apply_path(tmp_path, "apply/legacy-outcomes.csv", "rui") == \
        tmp_path / "profiles/rui/apply/legacy-outcomes.csv"


def test_a_checkout_from_before_the_data_pr_is_no_longer_read(tmp_path, capsys):
    # career-data before #65: profile files already under profiles/rui/, apply-run records still at the root
    profile(tmp_path, "rui")
    touch(tmp_path, "apply/log.csv", LOG_ROW)                          # a SUBMITTED row, no outcome
    touch(tmp_path, "apply/legacy-outcomes.csv", "site,job_id,reason\nglassdoor,42,old\n")
    touch(tmp_path, "logs/apply/glassdoor-2026-06-01.jsonl", '{"site": "glassdoor", "job_id": "42"}\n')
    root_before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    # the profile log is absent, so the strict check reads nothing and passes; the root records are ignored
    assert applylog.main(["check", "--strict", "--data", str(tmp_path), "--profile", "rui"]) == 0
    assert "ok, 0 rows" in capsys.readouterr().out
    assert applylog.main(["check", "--strict", "--data", str(tmp_path)]) == 0
    assert "ok, 0 rows" in capsys.readouterr().out
    assert not (tmp_path / "profiles/rui/apply/log.csv").exists()     # and nothing is created or moved
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == root_before


def test_apply_path_without_a_profile_folder_keeps_the_root_location(tmp_path):
    # pre-profile data repo (and the bank tests): the root path, as before ADR-071
    assert layout.apply_path(tmp_path, "logs/apply") == tmp_path / "logs/apply"
    assert layout.apply_path(tmp_path, "apply/log.csv") == tmp_path / "apply/log.csv"


def test_apply_path_with_a_profile_uses_the_profile_and_refuses_several_without_an_id(tmp_path):
    profile(tmp_path, "ana")
    assert layout.apply_path(tmp_path, "apply/log.csv") == tmp_path / "profiles/ana/apply/log.csv"
    profile(tmp_path, "bruno")
    with pytest.raises(ConfigError, match="--profile"):
        layout.apply_path(tmp_path, "apply/log.csv")
    assert layout.apply_path(tmp_path, "apply/log.csv", "bruno") == tmp_path / "profiles/bruno/apply/log.csv"


def test_applylog_cli_defaults_log_to_the_profile_when_data_is_given(tmp_path, capsys):
    profile(tmp_path, "rui")
    assert applylog.main(["upsert", "--data", str(tmp_path), "--site", "glassdoor", "--employer", "Acme",
                          "--role", "Dev", "--job-id", "42", "--status", "CANDIDATE",
                          "--date", "2026-06-01"]) == 0
    assert (tmp_path / "profiles/rui/apply/log.csv").is_file()
    assert not (tmp_path / "apply/log.csv").exists()
    assert applylog.main(["check", "--strict", "--data", str(tmp_path)]) == 0   # log omitted: profile's log
    assert "ok, 1 rows" in capsys.readouterr().out


def test_applylog_cli_explicit_log_still_wins_and_works_on_the_root_path(tmp_path, capsys):
    profile(tmp_path, "rui")
    touch(tmp_path, "apply/log.csv", LOG_ROW)                           # root copy, not yet moved
    assert applylog.main(["check", "--strict", "--data", str(tmp_path), "--log", str(tmp_path / "apply/log.csv")]) == 0
    assert "ok, 1 rows" in capsys.readouterr().out
    # the relative form from the data repo's cwd keeps working
    cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        assert applylog.main(["check", "--strict", "--data", ".", "--log", "apply/log.csv"]) == 0
    finally:
        os.chdir(cwd)
    assert "ok, 1 rows" in capsys.readouterr().out


def test_applylog_cli_without_log_or_data_is_an_error(capsys):
    assert applylog.main(["check"]) == 2
    assert "--data" in capsys.readouterr().err


def test_outcome_and_batch_write_under_the_profile(tmp_path, capsys):
    profile(tmp_path, "rui")
    o = bank.ApplyOutcome(job_id="1234", employer="Example Co", role="Engineer", site="greenhouse",
                          status="SUBMITTED", verified_by="confirmation_url", ts="2026-11-04")
    path = bank.append_outcome(o, data=str(tmp_path))
    assert path == tmp_path / "profiles/rui/logs/apply/greenhouse-2026-11-04.jsonl"
    rows = tmp_path / "rows.csv"
    rows.write_text("date,site,employer,role,job_id,status,verified_by,ts\n"
                    "2026-11-05,arc,Beta,Lead,9,SUBMITTED,site_applied_list,2026-11-05\n", encoding="utf-8")
    assert applylog.main(["batch", "--data", str(tmp_path), "--file", str(rows)]) == 0
    assert (tmp_path / "profiles/rui/apply/log.csv").is_file()
    assert (tmp_path / "profiles/rui/logs/apply/arc-2026-11-05.jsonl").is_file()
    assert not (tmp_path / "logs").exists()


# ---- phase C (issue #118): moved_path and the LEGACY rule ----

@pytest.fixture
def fresh_warnings():
    layout._warned.clear()


def test_moved_path_is_under_the_profile_when_nothing_exists_yet(tmp_path, fresh_warnings):
    profile(tmp_path, "rui")
    assert layout.moved_path(tmp_path, "state/seen.json") == tmp_path / "profiles/rui/state/seen.json"
    assert layout.moved_path(tmp_path, "logs/runs.jsonl") == tmp_path / "profiles/rui/logs/runs.jsonl"
    assert layout.moved_path(tmp_path, "applications/queue.json", "rui") == \
        tmp_path / "profiles/rui/applications/queue.json"


def test_moved_path_keeps_the_root_with_no_profile_folder(tmp_path, fresh_warnings):
    assert layout.moved_path(tmp_path, "reports/2026-01-01.md") == tmp_path / "reports/2026-01-01.md"


def test_a_new_file_in_an_existing_root_folder_stays_at_the_root(tmp_path, fresh_warnings):
    profile(tmp_path, "rui")
    touch(tmp_path, "reports/2026-01-01.md")
    assert layout.moved_path(tmp_path, "reports/2026-01-02.md") == tmp_path / "reports/2026-01-02.md"
    assert not (tmp_path / "profiles/rui/reports").exists()


def test_the_legacy_warning_is_printed_once_per_folder(tmp_path, capsys, fresh_warnings):
    profile(tmp_path, "rui")
    touch(tmp_path, "state/seen.json")
    layout.moved_path(tmp_path, "state/seen.json")
    layout.moved_path(tmp_path, "state/runs.jsonl")
    err = capsys.readouterr().err
    assert err.count("LEGACY") == 1 and "state" in err


def test_the_profile_folder_wins_when_both_exist(tmp_path, fresh_warnings):
    profile(tmp_path, "rui")
    touch(tmp_path, "state/seen.json")
    touch(tmp_path, "profiles/rui/state/other.json")
    assert layout.moved_path(tmp_path, "state/seen.json") == tmp_path / "profiles/rui/state/seen.json"


def test_the_runs_log_moves_as_one_file_not_with_logs(tmp_path, fresh_warnings):
    profile(tmp_path, "rui")
    touch(tmp_path, "logs/apply/.gitkeep", "")                       # a root logs/ folder alone
    assert layout.moved_path(tmp_path, "logs/runs.jsonl") == tmp_path / "profiles/rui/logs/runs.jsonl"
    touch(tmp_path, "logs/runs.jsonl", "{}\n")
    assert layout.moved_path(tmp_path, "logs/runs.jsonl") == tmp_path / "logs/runs.jsonl"


def test_several_profiles_use_the_root_only_while_it_holds_the_data(tmp_path, fresh_warnings):
    profile(tmp_path, "ana")
    profile(tmp_path, "bruno")
    with pytest.raises(ConfigError, match="--profile"):
        layout.moved_path(tmp_path, "state/seen.json")
    assert layout.moved_path(tmp_path, "state/seen.json", "bruno") == tmp_path / "profiles/bruno/state/seen.json"
    touch(tmp_path, "state/seen.json")
    assert layout.moved_path(tmp_path, "state/seen.json") == tmp_path / "state/seen.json"


def test_moved_name_is_relative_to_the_root(tmp_path, fresh_warnings):
    profile(tmp_path, "rui")
    assert layout.moved_name(tmp_path, "state/linkedin-cooldown.json") == \
        "profiles/rui/state/linkedin-cooldown.json"


def test_the_queue_is_read_and_written_at_the_root_while_legacy(tmp_path, fresh_warnings):
    from jobscan.apply.queue import Queue
    profile(tmp_path, "rui")
    touch(tmp_path, "applications/queue.json", json.dumps({"items": {"k1": {"candidate_key": "k1"}}}))
    q = Queue(tmp_path)
    assert "k1" in q.items
    q.add("k2", {"status": "queued"})
    q.save()
    assert "k2" in json.loads((tmp_path / "applications/queue.json").read_text())["items"]
    assert not (tmp_path / "profiles/rui/applications").exists()


def test_queue_and_answers_are_created_under_the_profile_when_no_root_folder(tmp_path, fresh_warnings):
    from jobscan.apply.answers import AnswerStore
    from jobscan.apply.queue import Queue
    profile(tmp_path, "rui")
    q = Queue(tmp_path)
    q.add("k1", {"status": "queued"})
    q.save()
    AnswerStore(tmp_path).save()
    assert (tmp_path / "profiles/rui/applications/queue.json").is_file()
    assert (tmp_path / "profiles/rui/applications/answers.json").is_file()
    assert not (tmp_path / "applications").exists()


def test_run_log_slug_cache_and_cooldown_use_a_moved_name(tmp_path, fresh_warnings):
    from jobscan.apply import linkedin, runlog
    from jobscan.apply.greenhouse import GreenhouseRef
    from jobscan.apply.slug_cache import SlugCache
    from jobscan.store import FileStore
    profile(tmp_path, "rui")
    store = FileStore(tmp_path)
    log = runlog.RunLog(store, file=layout.moved_name(tmp_path, runlog.FILE))
    log.finish(log.start("r1", "https://example.com/j"), "submitted")
    assert (tmp_path / "profiles/rui/logs/runs.jsonl").is_file()
    assert not (tmp_path / "logs/runs.jsonl").exists()

    cool = layout.moved_name(tmp_path, linkedin.COOLDOWN_FILE)
    linkedin.start_cooldown(store, 7, file=cool)
    assert (tmp_path / "profiles/rui/state/linkedin-cooldown.json").is_file()
    assert linkedin.cooldown_active(store, file=cool) is True
    assert linkedin.cooldown_active(store) is False                  # the default name is another file

    cache = SlugCache(store, file=layout.moved_name(tmp_path, "state/slug_cache.json"))
    assert cache.record(GreenhouseRef("acme", "123", "us"), 200)
    assert (tmp_path / "profiles/rui/state/slug_cache.json").is_file()


def test_seen_budget_and_journal_follow_the_state_folder(tmp_path, fresh_warnings):
    from jobscan.state import Budget, Journal, Seen
    profile(tmp_path, "rui")
    seen, budget, journal = Seen(tmp_path), Budget(tmp_path, {"adzuna": 5}), Journal(tmp_path)
    seen.add("k1", "Lead", "Acme")
    budget.spend("adzuna")
    journal.record("2026-01-01", "completed")
    for obj in (seen, budget, journal):
        obj.save()
    for name in ("seen", "budget", "delivery"):
        assert (tmp_path / f"profiles/rui/state/job-scan-{name}.json").is_file()
    assert not (tmp_path / "state").exists()


def test_seen_is_read_and_written_at_the_root_while_legacy(tmp_path, fresh_warnings):
    from jobscan.state import Seen
    profile(tmp_path, "rui")
    touch(tmp_path, "state/job-scan-seen.json", json.dumps({"k1": {}}))
    seen = Seen(tmp_path)
    assert "k1" in seen
    seen.add("k2", "Lead", "Acme")
    seen.save()
    assert set(json.loads((tmp_path / "state/job-scan-seen.json").read_text())) == {"k1", "k2"}
    assert not (tmp_path / "profiles/rui/state").exists()


def test_each_profile_has_its_own_seen_set(tmp_path, fresh_warnings):
    from jobscan.state import Seen
    profile(tmp_path, "ana")
    profile(tmp_path, "bruno")
    ana = Seen(tmp_path, "ana")
    ana.add("k1", "Lead", "Acme")
    ana.save()
    assert "k1" in Seen(tmp_path, "ana")
    assert "k1" not in Seen(tmp_path, "bruno")
    with pytest.raises(ConfigError, match="--profile"):
        Seen(tmp_path)


def test_decide_reads_the_queue_of_the_chosen_profile(tmp_path, fresh_warnings):
    from jobscan import decide
    profile(tmp_path, "ana")
    profile(tmp_path, "bruno")
    key = "abcdef12" + "0" * 24
    touch(tmp_path, "profiles/ana/applications/queue.json", json.dumps(
        {"items": {key: {"candidate_key": key, "status": "queued", "title": "Lead", "company": "Acme",
                         "profile": "ana"}}}))
    assert decide.main(["--data", str(tmp_path), "--title", "done abcdef12", "--profile", "ana"]) == 0
    saved = json.loads((tmp_path / "profiles/ana/applications/queue.json").read_text())
    assert saved["items"][key]["status"] == "done"


def test_preflight_creates_the_state_folder_under_the_profile(tmp_path, fresh_warnings):
    from jobscan.collect import preflight
    profile(tmp_path, "rui")
    preflight(tmp_path, {"profiles": []})
    assert (tmp_path / "profiles/rui/state").is_dir() and not (tmp_path / "state").exists()


def test_reports_follow_the_root_folder_while_legacy(tmp_path, fresh_warnings):
    profile(tmp_path, "rui")
    assert layout.moved_path(tmp_path, "reports/applications.md") == tmp_path / "profiles/rui/reports/applications.md"
    touch(tmp_path, "reports/2026-01-01.md")
    assert layout.moved_path(tmp_path, "reports/applications.md") == tmp_path / "reports/applications.md"


# ---- phase C, per-profile Seen and Budget in collect, report and clip ----

def _two_profile_repo(tmp_path):
    import yaml
    for pid in ("ana", "bruno"):
        touch(tmp_path, f"profiles/{pid}/profile.yaml", yaml.safe_dump(
            {"daily_queries": [{"source": "fake", "query": pid}]}))
        touch(tmp_path, f"profiles/{pid}/01-knowledge/05-job-match.md")
    touch(tmp_path, "config.yaml", "budgets: {fake: 5}\n")
    touch(tmp_path, "authorization.yaml", "active: true\n")


def test_collect_with_a_profile_uses_only_its_queries_seen_set_and_budget(tmp_path, monkeypatch, fresh_warnings):
    from jobscan import collect
    from jobscan.models import Candidate
    _two_profile_repo(tmp_path)
    asked = []

    def fake(query, profile, secrets=None):
        asked.append(profile)
        return [Candidate(candidate_key="k1", profile=profile, source="fake", title="Lead",
                          company="Acme", url="https://x.test/1")]

    monkeypatch.setattr(collect, "REGISTRY", {"fake": fake})
    out = tmp_path / "c.json"
    assert collect.main(["--data", str(tmp_path), "--out", str(out), "--profile", "ana"]) == 0
    assert asked == ["ana"]
    assert (tmp_path / "profiles/ana/state/job-scan-budget.json").is_file()
    assert not (tmp_path / "profiles/bruno/state/job-scan-budget.json").exists()
    assert not (tmp_path / "state").exists()


def test_collect_needs_a_profile_when_there_are_several_and_rejects_an_unknown_one(tmp_path, capsys, fresh_warnings):
    from jobscan import collect
    _two_profile_repo(tmp_path)
    out = tmp_path / "c.json"
    assert collect.main(["--data", str(tmp_path), "--out", str(out)]) == 2
    assert "--profile" in capsys.readouterr().err
    assert collect.main(["--data", str(tmp_path), "--out", str(out), "--profile", "nobody"]) == 2
    assert "unknown profile" in capsys.readouterr().err


def test_report_writes_state_and_report_under_the_chosen_profile(tmp_path, fresh_warnings):
    from jobscan import report
    _two_profile_repo(tmp_path)
    cands = touch(tmp_path, "candidates.json", json.dumps(
        {"generated_on": "2026-01-02", "candidates": [
            {"candidate_key": "k1", "title": "Lead", "company": "Acme"}]}))
    decs = touch(tmp_path, "decisions.json", "[]")
    base = ["--data", str(tmp_path), "--candidates", str(cands), "--decisions", str(decs),
            "--out-dir", str(tmp_path / "out")]
    assert report.main([*base, "--profile", "ana", "--commit"]) == 0
    assert (tmp_path / "profiles/ana/reports/2026-01-02.md").is_file()
    assert "k1" in json.loads((tmp_path / "profiles/ana/state/job-scan-seen.json").read_text())
    assert not (tmp_path / "profiles/bruno/state").exists()
    assert not (tmp_path / "reports").exists() and not (tmp_path / "state").exists()


def test_report_with_several_profiles_and_no_choice_is_a_config_error_not_a_traceback(tmp_path, capsys, fresh_warnings):
    from jobscan import report
    _two_profile_repo(tmp_path)
    cands = touch(tmp_path, "candidates.json", json.dumps({"generated_on": "2026-01-02", "candidates": []}))
    decs = touch(tmp_path, "decisions.json", "[]")
    args = ["--data", str(tmp_path), "--candidates", str(cands), "--decisions", str(decs)]
    assert report.main(args) == 2 and "config error" in capsys.readouterr().err
    # root state exists but the root reports folder does not: still an error exit, not a traceback
    touch(tmp_path, "state/job-scan-delivery.json", json.dumps({"runs": []}))
    assert report.main(args) == 2 and "config error" in capsys.readouterr().err


def test_a_seen_set_belongs_to_one_profile(tmp_path, fresh_warnings):
    from jobscan.state import Seen
    _two_profile_repo(tmp_path)
    seen = Seen(tmp_path, "bruno")
    seen.add("k1", "Lead", "Acme")
    seen.save()
    assert (tmp_path / "profiles/bruno/state/job-scan-seen.json").is_file()
    assert "k1" not in Seen(tmp_path, "ana")
