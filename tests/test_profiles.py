import pytest
import yaml

from jobscan.config import ConfigError, load_config


def write(root, rel, data):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def test_profiles_load_from_their_folders(tmp_path):
    write(tmp_path, "config.yaml", {"budgets": {"jsearch": 5}})
    write(tmp_path, "profiles/ana/profile.yaml", {"display_name": "Ana", "weekly_day": 2})
    write(tmp_path, "profiles/bruno/profile.yaml", {"criteria": "custom.md"})
    (tmp_path / "profiles/notes").mkdir()            # a folder without profile.yaml is ignored
    cfg = load_config(tmp_path)
    assert [p["id"] for p in cfg["profiles"]] == ["ana", "bruno"]
    ana, bruno = cfg["profiles"]
    assert ana["weekly_day"] == 2 and ana["criteria"] == "profiles/ana/01-knowledge/05-job-match.md"
    assert bruno["criteria"] == "custom.md"           # an explicit value wins
    assert cfg["budgets"] == {"jsearch": 5}           # global settings untouched


def test_inline_profiles_still_load_alongside_files(tmp_path):
    write(tmp_path, "config.yaml", {"profiles": [{"id": "old", "display_name": "Old"}]})
    write(tmp_path, "profiles/new/profile.yaml", {"display_name": "New"})
    assert [p["id"] for p in load_config(tmp_path)["profiles"]] == ["old", "new"]


def test_same_id_in_both_places_is_an_error(tmp_path):
    write(tmp_path, "config.yaml", {"profiles": [{"id": "ana"}]})
    write(tmp_path, "profiles/ana/profile.yaml", {})
    with pytest.raises(ConfigError, match="defined in config.yaml and in"):
        load_config(tmp_path)


def test_id_must_match_the_folder(tmp_path):
    write(tmp_path, "config.yaml", {})
    write(tmp_path, "profiles/ana/profile.yaml", {"id": "bruno"})
    with pytest.raises(ConfigError, match="must match its folder"):
        load_config(tmp_path)


def test_no_profiles_is_an_error(tmp_path):
    write(tmp_path, "config.yaml", {"budgets": {}})
    with pytest.raises(ConfigError, match="no profiles"):
        load_config(tmp_path)
