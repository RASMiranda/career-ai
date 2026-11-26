"""Phase C end (issue #123, ADR-075 c): the LEGACY root fallbacks are gone.

Every profile file lives under profiles/<id>/. A root copy of a name that moved (reports/, state/,
applications/, logs/runs.jsonl, the apply section of config.yaml, logs/apply/ failure lines) is never
read or written, and a data repo with no profile folder is a ConfigError, not a root fallback.
"""

import json
from pathlib import Path

import pytest
import yaml

from jobscan import layout
from jobscan.config import ConfigError, load_config

SRC = Path(__file__).resolve().parents[1] / "src" / "jobscan"


def touch(root: Path, rel: str, text: str = "x\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def profile(root: Path, pid: str) -> None:
    touch(root, f"profiles/{pid}/profile.yaml", "display_name: Synthetic\n")


# ---- layout: moved names resolve to the profile only ----

def test_moved_names_resolve_to_the_profile_even_when_a_root_copy_exists(tmp_path, capsys):
    profile(tmp_path, "rui")
    touch(tmp_path, "state/job-scan-seen.json", "{}")
    touch(tmp_path, "reports/2026-01-01.md")
    touch(tmp_path, "logs/runs.jsonl", "{}\n")
    touch(tmp_path, "applications/queue.json", "{}")
    assert layout.moved_path(tmp_path, "state/job-scan-seen.json") == \
        tmp_path / "profiles/rui/state/job-scan-seen.json"
    assert layout.moved_path(tmp_path, "reports/2026-01-02.md") == tmp_path / "profiles/rui/reports/2026-01-02.md"
    assert layout.moved_path(tmp_path, "logs/runs.jsonl") == tmp_path / "profiles/rui/logs/runs.jsonl"
    assert layout.moved_path(tmp_path, "applications/queue.json") == \
        tmp_path / "profiles/rui/applications/queue.json"
    assert "LEGACY" not in capsys.readouterr().err


def test_moved_path_without_a_profile_folder_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match=r"profiles/<id>/profile\.yaml"):
        layout.moved_path(tmp_path, "reports/2026-01-01.md")


def test_apply_path_without_a_profile_folder_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="no profile"):
        layout.apply_path(tmp_path, "logs/apply")


def test_several_profiles_without_an_id_is_a_config_error_even_with_a_root_copy(tmp_path):
    profile(tmp_path, "ana")
    profile(tmp_path, "bruno")
    touch(tmp_path, "state/job-scan-seen.json", "{}")
    with pytest.raises(ConfigError, match="--profile"):
        layout.moved_path(tmp_path, "state/job-scan-seen.json")


def test_moved_name_under_the_profile(tmp_path):
    profile(tmp_path, "rui")
    assert layout.moved_name(tmp_path, "state/linkedin-cooldown.json") == \
        "profiles/rui/state/linkedin-cooldown.json"


def test_the_fallback_names_are_gone_from_layout():
    for name in ("MOVED_FOLDERS", "MOVED_FILES", "_warned", "_legacy_unit"):
        assert not hasattr(layout, name), name


# ---- no LEGACY code is left in src (only the apply-run record names) ----

def test_legacy_appears_only_in_the_applylog_names():
    hits = []
    for path in SRC.rglob("*.py"):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "LEGACY" in line:
                hits.append(f"{path.relative_to(SRC)}:{n}")
    assert hits and all(h.startswith("applylog.py:") for h in hits), hits


# ---- publish: profile forms only ----

def test_publish_paths_are_the_profile_forms_only(tmp_path):
    from jobscan import pipeline
    profile(tmp_path, "ana")
    profile(tmp_path, "bruno")
    paths = pipeline.publish_paths(tmp_path)
    assert paths == [f"profiles/{pid}/{p}" for pid in ("ana", "bruno")
                     for p in ("reports", "state", "applications/queue.json")]
    assert not any(not p.startswith("profiles/") for p in paths)


# ---- apply settings: the profile file only ----

def _apply_repo(tmp_path, ids=("ana",), root_apply=None, own=None):
    for pid in ids:
        profile(tmp_path, pid)
        touch(tmp_path, f"profiles/{pid}/01-knowledge/05-job-match.md")
    touch(tmp_path, "config.yaml", yaml.safe_dump({"apply": root_apply} if root_apply else {"budgets": {}}))
    for pid, section in (own or {}).items():
        touch(tmp_path, f"profiles/{pid}/apply/config.yaml", yaml.safe_dump(section))


def test_the_root_apply_section_is_ignored_with_no_warning(tmp_path, capsys):
    from jobscan.apply import policy
    _apply_repo(tmp_path, root_apply={"mode": "assisted"})
    cfg = load_config(tmp_path)
    assert policy.apply_cfg(cfg, "ana")["mode"] == "manual"
    assert policy.apply_cfg(cfg)["mode"] == "manual"
    assert capsys.readouterr().err == ""


def test_an_unknown_profile_id_is_a_config_error(tmp_path):
    from jobscan.apply import policy
    _apply_repo(tmp_path)
    with pytest.raises(ConfigError, match="unknown profile"):
        policy.apply_cfg(load_config(tmp_path), "nobody")


def test_no_profile_id_with_several_profiles_is_a_config_error(tmp_path):
    from jobscan.apply import policy
    _apply_repo(tmp_path, ("ana", "bruno"), own={"ana": {"mode": "auto"}})
    cfg = load_config(tmp_path)
    assert policy.apply_cfg(cfg, "ana")["mode"] == "auto"
    with pytest.raises(ConfigError, match="--profile"):
        policy.apply_cfg(cfg)


def test_no_profile_id_with_one_profile_uses_it(tmp_path):
    from jobscan.apply import policy
    _apply_repo(tmp_path, own={"ana": {"mode": "off"}})
    assert policy.apply_cfg(load_config(tmp_path))["mode"] == "off"


# ---- failure lines: profile folders only ----

def _fail_entry(key="k1"):
    return {"candidate_key": key, "ats": "greenhouse", "error_code": "FORM_CHANGED", "step": "fill"}


def test_a_failure_line_with_no_profile_folder_is_a_config_error(tmp_path):
    from jobscan.apply.faillog import FailureLog
    with pytest.raises(ConfigError):
        FailureLog(tmp_path).write(_fail_entry(), None)
    assert not (tmp_path / "logs").exists()


def test_read_since_ignores_a_stale_root_logs_folder(tmp_path):
    from jobscan.apply.faillog import FailureLog
    profile(tmp_path, "rui")
    touch(tmp_path, "logs/apply/2026-01-01.jsonl",
          json.dumps({"at": "2999-01-01T00:00:00+00:00", "candidate_key": "root"}) + "\n")
    FailureLog(tmp_path).write(_fail_entry("kr"), "rui")
    assert [r["candidate_key"] for r in FailureLog(tmp_path).read_since(1)] == ["kr"]


def test_read_since_with_no_profile_folder_is_empty(tmp_path):
    from jobscan.apply.faillog import FailureLog
    touch(tmp_path, "logs/apply/2026-01-01.jsonl", "{}\n")
    assert FailureLog(tmp_path).read_since(1) == []


def test_an_unknown_profile_failure_line_is_skipped_with_one_warning(tmp_path, capsys):
    from jobscan.apply.faillog import FailureLog
    profile(tmp_path, "rui")
    log = FailureLog(tmp_path)
    assert log.write(_fail_entry(), "nobody") is None
    assert log.write(_fail_entry(), None) is None
    assert capsys.readouterr().err.count("warning") == 1
    assert not (tmp_path / "logs").exists()
