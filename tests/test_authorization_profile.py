"""authorization.yaml is read from the profile folder only, and fails closed (issue #125, ADR-075 d, ADR-042).

``profiles/<id>/authorization.yaml`` is the only file ever read. A root ``authorization.yaml`` is never read,
with or without a profile copy. A missing or unreadable file is never authorized.
"""

from pathlib import Path

import pytest
import yaml

from jobscan import validate
from jobscan.config import ConfigError, load_authorization

SRC = Path(__file__).resolve().parents[1] / "src" / "jobscan"


def ensure_profile(root: Path, pid: str) -> None:
    """A profile folder with its profile.yaml (the folder name is the id)."""
    write(root / "profiles" / pid / "profile.yaml", "display_name: Synthetic\n")


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else yaml.safe_dump(data), encoding="utf-8")


def repo(tmp_path: Path, *ids: str) -> Path:
    for pid in ids or ("rui",):
        ensure_profile(tmp_path, pid)
    return tmp_path


def test_the_profile_copy_is_what_is_read(tmp_path):
    root = repo(tmp_path)
    write(root / "profiles/rui/authorization.yaml", {"active": True, "application_submission": {"master_switch": False}})
    auth = load_authorization(root, "rui")
    assert auth["active"] is True and auth["application_submission"]["master_switch"] is False


def test_a_root_copy_is_never_read_even_when_the_profile_copy_is_missing(tmp_path):
    root = repo(tmp_path)
    write(root / "authorization.yaml", {"active": True})
    with pytest.raises(ConfigError) as info:
        load_authorization(root, "rui")
    message = str(info.value)
    assert "profiles/rui/authorization.yaml" in message and "root copy is not read" in message


def test_a_root_copy_is_ignored_when_a_profile_copy_exists(tmp_path):
    root = repo(tmp_path)
    write(root / "authorization.yaml", {"active": True})
    write(root / "profiles/rui/authorization.yaml", {"active": False})
    assert load_authorization(root, "rui")["active"] is False


def test_an_unreadable_profile_copy_is_a_config_error_not_authorized(tmp_path):
    root = repo(tmp_path)
    write(root / "profiles/rui/authorization.yaml", "active: [unclosed\n")
    with pytest.raises(ConfigError, match=r"profiles/rui/authorization\.yaml"):
        load_authorization(root, "rui")


def test_an_empty_profile_copy_is_not_active(tmp_path):
    root = repo(tmp_path)
    write(root / "profiles/rui/authorization.yaml", "")
    assert not load_authorization(root, "rui").get("active")


def test_several_profiles_without_an_id_must_say_which(tmp_path):
    root = repo(tmp_path, "ana", "bruno")
    write(root / "profiles/ana/authorization.yaml", {"active": True})
    with pytest.raises(ConfigError, match="--profile"):
        load_authorization(root, None)
    assert load_authorization(root, "ana")["active"] is True


def test_no_profile_folder_is_a_config_error(tmp_path):
    write(tmp_path / "authorization.yaml", {"active": True})
    with pytest.raises(ConfigError, match="no profile"):
        load_authorization(tmp_path, None)


def test_validate_fails_hard_when_the_profile_copy_is_missing(tmp_path, capsys):
    root = repo(tmp_path)
    write(root / "config.yaml", yaml.safe_dump({}))
    write(root / "authorization.yaml", {"active": True})       # a root copy is not enough
    write(root / "candidates.json", {"candidates": []})
    write(root / "decisions.json", [])
    rc = validate.main(["--data", str(root), "--candidates", str(root / "candidates.json"),
                        "--decisions", str(root / "decisions.json")])
    assert rc == 2
    assert "profiles/rui/authorization.yaml" in capsys.readouterr().err


def test_pipeline_stop_names_the_profile_path_and_runs_nothing(tmp_path, capsys):
    from jobscan import pipeline
    root = repo(tmp_path)
    write(root / "profiles/rui/authorization.yaml", {"active": False})
    write(root / "config.yaml", yaml.safe_dump({}))
    args = type("A", (), {"data": str(root), "work": str(tmp_path / "w"), "profile": None})
    assert pipeline._setup(args) is None
    err = capsys.readouterr().err
    assert "profiles/rui/authorization.yaml" in err and "nothing was run" in err


def test_no_read_of_a_root_authorization_file_remains_in_src():
    offenders = []
    for path in SRC.rglob("*.py"):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if 'root / "authorization.yaml"' in code or "root/\"authorization.yaml\"" in code:
                offenders.append(f"{path.relative_to(SRC)}:{n}")
    assert offenders == []
