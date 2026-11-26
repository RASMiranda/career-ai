"""Shared test helper: a data repo with one profile folder (ADR-075 c, issue #123).

Tests that exercise profile-scoped code (queue, failure log, apply settings) call ``ensure_profile``
on their ``tmp_path``. The profile id is ``p`` unless a test names another one.
"""

from pathlib import Path


def ensure_profile(root, pid: str = "p") -> Path:
    folder = Path(root) / "profiles" / pid
    folder.mkdir(parents=True, exist_ok=True)
    profile = folder / "profile.yaml"
    if not profile.exists():
        profile.write_text("display_name: Synthetic\n", encoding="utf-8")
    return folder


def write_profile(root, pid: str, data: dict) -> Path:
    """profiles/<pid>/profile.yaml with ``data`` (the folder name is the id; no id key is written)."""
    import yaml
    folder = ensure_profile(root, pid)
    (folder / "profile.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    return folder


def write_apply_config(root, pid: str, data: dict) -> Path:
    """profiles/<pid>/apply/config.yaml: the apply settings of one profile (ADR-075 c)."""
    import yaml
    path = Path(root) / "profiles" / pid / "apply" / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path
