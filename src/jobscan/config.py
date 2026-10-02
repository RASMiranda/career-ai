"""Configuration lives in the private data repo, never here."""

import os
from pathlib import Path

import yaml


class ConfigError(RuntimeError):
    pass


def data_root(explicit: str | None = None) -> Path:
    root = explicit or os.environ.get("CAREER_DATA")
    if not root:
        raise ConfigError(
            "Set --data or CAREER_DATA to the path of the private data repo."
        )
    path = Path(root).expanduser().resolve()
    if not path.is_dir():
        raise ConfigError(f"Data repo not found: {path}")
    return path


def load_config(root: Path) -> dict:
    cfg_path = root / "config.yaml"
    if not cfg_path.is_file():
        raise ConfigError(f"Missing {cfg_path}")
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    if not cfg.get("profiles"):
        raise ConfigError("config.yaml defines no profiles")
    return cfg


def load_authorization(root: Path) -> dict:
    auth_path = root / "authorization.yaml"
    if not auth_path.is_file():
        raise ConfigError(f"Missing {auth_path}")
    return yaml.safe_load(auth_path.read_text(encoding="utf-8")) or {}


def secret(name: str) -> str | None:
    """Read a credential from the environment. Values are never logged."""
    value = os.environ.get(name)
    return value or None
