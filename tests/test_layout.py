"""Profile file layout (ADR-069, ADR-070): every profile file lives under profiles/<id>/, there is no
root-path fallback, and a command needs a profile id (explicit, or the only profile folder)."""

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
