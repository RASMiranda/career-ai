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


PROFILE_FILE = "profile.yaml"
DEFAULT_CRITERIA = "profiles/{id}/01-knowledge/05-job-match.md"


def _load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name} must be a mapping")
    return data


def load_profiles(root: Path, inline: list | None = None) -> list[dict]:
    """Profiles live in ``profiles/<id>/profile.yaml``; the folder name is the id.

    Profiles still written inline under ``profiles:`` in config.yaml are accepted
    too (an id may not be defined in both places).
    """
    profiles = {p["id"]: p for p in (inline or []) if isinstance(p, dict) and p.get("id")}
    base = root / "profiles"
    for path in sorted(base.glob(f"*/{PROFILE_FILE}")) if base.is_dir() else []:
        pid = path.parent.name
        data = _load_yaml(path)
        if data.get("id", pid) != pid:
            raise ConfigError(f"{path.relative_to(root)}: id {data['id']!r} must match its folder {pid!r}")
        if pid in profiles:
            raise ConfigError(f"profile {pid!r} is defined in config.yaml and in {path.relative_to(root)}")
        profiles[pid] = {**data, "id": pid}
    for pid, profile in profiles.items():
        profile.setdefault("criteria", DEFAULT_CRITERIA.format(id=pid))
    return list(profiles.values())


def load_config(root: Path) -> dict:
    cfg_path = root / "config.yaml"
    if not cfg_path.is_file():
        raise ConfigError(f"Missing {cfg_path}")
    cfg = _load_yaml(cfg_path)
    cfg["profiles"] = load_profiles(root, cfg.get("profiles"))
    if not cfg["profiles"]:
        raise ConfigError(f"no profiles: add profiles/<id>/{PROFILE_FILE} (or profiles: in config.yaml)")
    return cfg


def load_authorization(root: Path) -> dict:
    auth_path = root / "authorization.yaml"
    if not auth_path.is_file():
        raise ConfigError(f"Missing {auth_path}")
    return yaml.safe_load(auth_path.read_text(encoding="utf-8")) or {}


def recipients(profile: dict) -> list[str]:
    """Addresses this profile's scan email goes to (profile.yaml → notify.email)."""
    raw = (profile.get("notify") or {}).get("email") or []
    if isinstance(raw, str):
        raw = [raw]
    return [a.strip() for a in raw if isinstance(a, str) and a.strip()]


def recipient_problems(cfg: dict) -> list[str]:
    """Every profile needs at least one plausible, non-placeholder address."""
    problems = []
    for profile in cfg.get("profiles", []):
        pid = profile.get("id", "?")
        addrs = recipients(profile)
        if not addrs:
            problems.append(f"profile {pid!r} has no notify.email")
        for a in addrs:
            local, _, domain = a.partition("@")
            if not local or "." not in domain or any(c.isspace() for c in a):
                problems.append(f"profile {pid!r} has an invalid address {a!r}")
            elif "REPLACE" in a.upper() or domain.lower().endswith("example.com"):
                problems.append(f"profile {pid!r} still has a placeholder address")
    return problems


def secret(name: str) -> str | None:
    """Read a credential from the environment. Values are never logged."""
    value = os.environ.get(name)
    return value or None
