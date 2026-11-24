"""Profile file layout (ADR-069, ADR-070): every profile file lives under profiles/<id>/, there is no
root-path fallback, and a command needs a profile id (explicit, or the only profile folder)."""

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


# ---- ADR-071 phase B: apply-run records under profiles/<id>/, with a root fallback until the data PR ----

from jobscan import applylog, bank  # noqa: E402

LOG_ROW = "date,site,employer,role,job_id,status\n2026-06-01,glassdoor,Acme,Dev,42,CANDIDATE\n"


def test_apply_log_new_location_wins_when_both_exist(tmp_path):
    profile(tmp_path, "rui")
    touch(tmp_path, "profiles/rui/apply/log.csv", LOG_ROW)
    touch(tmp_path, "apply/log.csv", "root copy, ignored\n")
    assert layout.resolve(tmp_path, "rui", "apply/log.csv") == tmp_path / "profiles/rui/apply/log.csv"


def test_apply_log_only_at_the_root_is_read_and_written_there(tmp_path):
    profile(tmp_path, "rui")
    touch(tmp_path, "apply/log.csv", LOG_ROW)                          # before the data PR
    path = layout.resolve(tmp_path, "rui", "apply/log.csv")
    assert path == tmp_path / "apply/log.csv"
    applylog.append(path, site="glassdoor", employer="Beta", role="Lead", job_id="43",
                    status="SUBMITTED", when="2026-06-02")
    assert len(applylog.read(tmp_path / "apply/log.csv")) == 2        # history stays in one file
    assert not (tmp_path / "profiles/rui/apply/log.csv").exists()


def test_apply_log_created_at_the_profile_path_when_it_exists_nowhere(tmp_path):
    profile(tmp_path, "rui")
    path = layout.resolve(tmp_path, "rui", "apply/log.csv")
    assert path == tmp_path / "profiles/rui/apply/log.csv"
    applylog.upsert(path, site="glassdoor", employer="Acme", role="Dev", job_id="1",
                    status="CANDIDATE", when="2026-06-01")
    assert path.is_file() and not (tmp_path / "apply/log.csv").exists()


def test_legacy_outcomes_follow_the_same_rule(tmp_path):
    profile(tmp_path, "rui")
    assert layout.resolve(tmp_path, "rui", "apply/legacy-outcomes.csv") == \
        tmp_path / "profiles/rui/apply/legacy-outcomes.csv"
    touch(tmp_path, "apply/legacy-outcomes.csv", "site,job_id,reason\n")
    assert layout.resolve(tmp_path, "rui", "apply/legacy-outcomes.csv") == \
        tmp_path / "apply/legacy-outcomes.csv"
    touch(tmp_path, "profiles/rui/apply/legacy-outcomes.csv", "site,job_id,reason\n")
    assert layout.resolve(tmp_path, "rui", "apply/legacy-outcomes.csv") == \
        tmp_path / "profiles/rui/apply/legacy-outcomes.csv"


def test_logs_apply_folder_new_wins_then_legacy_then_created_under_the_profile(tmp_path):
    profile(tmp_path, "rui")
    assert layout.resolve(tmp_path, "rui", "logs/apply") == tmp_path / "profiles/rui/logs/apply"  # neither
    touch(tmp_path, "logs/apply/greenhouse-2026-11-11.jsonl", "{}\n")
    assert layout.resolve(tmp_path, "rui", "logs/apply") == tmp_path / "logs/apply"              # legacy only
    touch(tmp_path, "profiles/rui/logs/apply/arc-2026-11-12.jsonl", "{}\n")
    assert layout.resolve(tmp_path, "rui", "logs/apply") == tmp_path / "profiles/rui/logs/apply"  # new wins


def test_names_not_in_legacy_have_no_root_fallback(tmp_path):
    profile(tmp_path, "rui")
    touch(tmp_path, "logs/runs.jsonl", "{}\n")
    touch(tmp_path, "applications/queue.json", "{}")
    assert layout.resolve(tmp_path, "rui", "logs/runs.jsonl") == tmp_path / "profiles/rui/logs/runs.jsonl"
    assert layout.resolve(tmp_path, "rui", "applications/queue.json") == \
        tmp_path / "profiles/rui/applications/queue.json"


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
