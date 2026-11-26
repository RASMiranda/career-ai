"""Stale root data refused (issue #123, ADR-075 c and d).

A non-empty root reports/, state/ or applications/ folder, or a non-empty root logs/runs.jsonl, is data
from before the profile move. Every command that loads config refuses to run and names the root path and
the profile path to move it to. Empty folders and an empty file do not count.
"""

from pathlib import Path

import pytest
import yaml

from jobscan import collect, validate
from jobscan.config import ConfigError, load_config
from profile_helpers import ensure_profile


def make_repo(tmp_path: Path, pid: str = "rui") -> Path:
    ensure_profile(tmp_path, pid)
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({"blacklist": {"companies": []}}))
    return tmp_path


@pytest.mark.parametrize("rel, make", [
    ("reports/2026-01-01.md", lambda p: p.write_text("# report\n")),
    ("state/job-scan-seen.json", lambda p: p.write_text("{}")),
    ("applications/queue.json", lambda p: p.write_text("{}")),
    ("logs/runs.jsonl", lambda p: p.write_text("{}\n")),
])
def test_a_non_empty_root_file_or_folder_is_refused(tmp_path, rel, make):
    root = make_repo(tmp_path)
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    make(target)
    with pytest.raises(ConfigError) as info:
        load_config(root)
    message = str(info.value)
    top = rel.split("/")[0]
    assert f"{top}" in message and "profiles/rui/" in message


def test_a_gitkeep_makes_a_root_folder_non_empty(tmp_path):
    root = make_repo(tmp_path)
    (root / "state").mkdir()
    (root / "state" / ".gitkeep").write_text("")
    with pytest.raises(ConfigError, match="state"):
        load_config(root)


def test_empty_root_folders_and_an_empty_runs_file_pass(tmp_path):
    root = make_repo(tmp_path)
    for name in ("reports", "state", "applications"):
        (root / name).mkdir()
    (root / "logs").mkdir()
    (root / "logs" / "runs.jsonl").write_text("")
    assert load_config(root)["profiles"][0]["id"] == "rui"


def test_no_root_data_at_all_passes(tmp_path):
    root = make_repo(tmp_path)
    assert load_config(root)["profiles"][0]["id"] == "rui"


def test_the_message_names_the_root_path_and_the_profile_path(tmp_path):
    root = make_repo(tmp_path)
    (root / "reports").mkdir()
    (root / "reports" / "old.md").write_text("x")
    with pytest.raises(ConfigError) as info:
        load_config(root)
    message = str(info.value)
    assert "reports/" in message and "profiles/rui/reports/" in message


def test_several_profiles_name_the_id_placeholder(tmp_path):
    make_repo(tmp_path, "ana")
    ensure_profile(tmp_path, "bruno")
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "seen.json").write_text("{}")
    with pytest.raises(ConfigError, match=r"profiles/<id>/state/"):
        load_config(tmp_path)


def test_validate_refuses_the_same_way(tmp_path, capsys):
    root = make_repo(tmp_path)
    (root / "applications").mkdir()
    (root / "applications" / "queue.json").write_text("{}")
    (root / "authorization.yaml").write_text("active: true\n")
    assert validate.main(["--data", str(root)]) == 2
    assert "profiles/rui/applications/" in capsys.readouterr().err


def test_collect_preflight_refuses_the_same_way(tmp_path, capsys):
    root = make_repo(tmp_path)
    (root / "reports").mkdir()
    (root / "reports" / "old.md").write_text("x")
    assert collect.main(["--data", str(root), "--preflight-only"]) == 2
    assert "profiles/rui/reports/" in capsys.readouterr().err


def test_the_guard_does_not_import_layout():
    src = (Path(__file__).resolve().parents[1] / "src" / "jobscan" / "config.py").read_text(encoding="utf-8")
    assert "from . import layout" not in src and "from .layout" not in src and "import layout" not in src
