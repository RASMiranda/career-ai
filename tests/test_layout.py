"""Profile file layout (ADR-069, phase A): the profile-folder copy wins, the data-root copy is a fallback,
a file that is created goes to the profile folder, and several profiles need an explicit --profile."""

import hashlib
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


def test_the_new_path_wins_over_the_legacy_one(tmp_path):
    profile(tmp_path, "rui")
    touch(tmp_path, "answer_bank.yaml", "legacy\n")
    new = touch(tmp_path, "profiles/rui/answer_bank.yaml", "new\n")
    assert layout.resolve(tmp_path, "rui", "answer_bank.yaml") == new


def test_the_legacy_root_path_is_read_until_the_data_moves(tmp_path):
    profile(tmp_path, "rui")
    legacy = touch(tmp_path, "apply/triage.yaml", "keywords\n")
    assert layout.resolve(tmp_path, "rui", "apply/triage.yaml") == legacy
    state = touch(tmp_path, "state/cv_manifest.json", "{}")
    assert layout.resolve(tmp_path, "rui", "cv_manifest.json") == state
    docs = touch(tmp_path, "docs/OPEN-QUESTIONS.md", "# q\n")
    assert layout.resolve(tmp_path, "rui", "OPEN-QUESTIONS.md") == docs


def test_a_created_file_goes_to_the_new_path(tmp_path):
    profile(tmp_path, "rui")
    expected = tmp_path / "profiles/rui/apply/answer-bank.yaml"
    assert layout.resolve(tmp_path, "rui", "apply/answer-bank.yaml") == expected
    touch(tmp_path, "profiles/rui/apply/answer-bank.yaml", "new\n")
    assert layout.resolve(tmp_path, "rui", "apply/answer-bank.yaml") == expected
    assert not (tmp_path / "apply/answer-bank.yaml").exists()           # nothing written at the root


def test_the_profile_copy_is_preferred_even_when_the_legacy_one_is_newer(tmp_path):
    profile(tmp_path, "rui")
    touch(tmp_path, "state/rate_card.json", "{}")
    new = touch(tmp_path, "profiles/rui/rate_card.json", "{}")
    assert layout.resolve(tmp_path, "rui", "rate_card.json") == new


def test_several_profiles_without_an_explicit_id_is_a_config_error(tmp_path):
    profile(tmp_path, "ana")
    profile(tmp_path, "bruno")
    with pytest.raises(ConfigError, match="--profile"):
        layout.default_profile(tmp_path)
    assert layout.default_profile(tmp_path, "bruno") == "bruno"       # explicit always wins


def test_one_profile_is_the_default_and_none_means_legacy_only(tmp_path):
    assert layout.default_profile(tmp_path) is None                    # no profile folder: legacy paths
    profile(tmp_path, "rui")
    touch(tmp_path, "profiles/notes/readme.md")                         # a folder without profile.yaml
    assert layout.default_profile(tmp_path) == "rui"


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


def test_cv_check_with_several_profiles_needs_the_profile_flag(tmp_path, capsys):
    profile(tmp_path, "ana")
    profile(tmp_path, "bruno")
    assert main(["cv-check", "--data", str(tmp_path)]) == 2
    assert "--profile" in capsys.readouterr().err
    assert main(["cv-check", "--data", str(tmp_path), "--profile", "ana"]) == 2   # no manifest yet, still named
    assert "no cv_manifest.json" in capsys.readouterr().err


def test_cv_check_legacy_state_manifest_keys_stay_relative_to_the_data_root(tmp_path):
    profile(tmp_path, "rui")
    data = b"CV card, synthetic\n"
    touch(tmp_path, "profiles/rui/cv/general.md", data.decode())
    manifest = {"profiles/rui/cv/general.md": hashlib.sha256(data).hexdigest()}
    touch(tmp_path, "state/cv_manifest.json", json.dumps(manifest))
    report = cvcheck.check(tmp_path, "rui")
    assert report.fresh and report.checked == 1
