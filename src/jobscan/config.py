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
APPLY_CONFIG = "apply/config.yaml"  # inside a profile folder: that profile's apply settings (phase C)
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


# ADR-075 c: data that moved under profiles/<id>/. A non-empty root copy is stale and is refused before
# anything is read or written. Relative names: a folder ("reports") or a file ("logs/runs.jsonl").
STALE_ROOT = ("reports", "state", "applications", "logs/runs.jsonl")


def stale_root_error(root_rel: str, profile_rel: str, what: str = "data") -> ConfigError:
    """The one message for a stale root copy (ADR-075 c, d): names the root path and the profile path."""
    return ConfigError(f"{what} at the data repo root ({root_rel}) is stale: it moved to {profile_rel} "
                       "(ADR-075). Move it there, or remove the root copy. Nothing was read or written.")


def _non_empty(path: Path) -> bool:
    """A folder with any entry (a .gitkeep counts) or a file with bytes in it."""
    if path.is_dir():
        return any(path.iterdir())
    if path.is_file():
        return path.stat().st_size > 0
    return False


def _check_stale_root(root: Path) -> None:
    base = root / "profiles"
    ids = sorted(p.parent.name for p in base.glob(f"*/{PROFILE_FILE}") if p.is_file()) if base.is_dir() else []
    pid = ids[0] if len(ids) == 1 else "<id>"
    for rel in STALE_ROOT:
        path = root / rel
        if _non_empty(path):
            shown = f"{rel}/" if path.is_dir() else rel
            raise stale_root_error(shown, f"profiles/{pid}/{shown}")


def load_config(root: Path) -> dict:
    _check_stale_root(root)
    cfg_path = root / "config.yaml"
    if not cfg_path.is_file():
        raise ConfigError(f"Missing {cfg_path}")
    cfg = _load_yaml(cfg_path)
    cfg["profiles"] = load_profiles(root, cfg.get("profiles"))
    if not cfg["profiles"]:
        raise ConfigError(f"no profiles: add profiles/<id>/{PROFILE_FILE} (or profiles: in config.yaml)")
    for profile in cfg["profiles"]:
        own = root / "profiles" / profile["id"] / APPLY_CONFIG
        if own.is_file():
            profile["apply_config"] = _load_yaml(own)
    return cfg


AUTH_FILE = "authorization.yaml"


def _profile_folder_ids(root: Path) -> list[str]:
    """Folder names under profiles/ that hold a profile.yaml, sorted (the folder name is the id)."""
    base = root / "profiles"
    if not base.is_dir():
        return []
    return sorted(p.parent.name for p in base.glob(f"*/{PROFILE_FILE}") if p.is_file())


def load_authorization(root: Path, pid: str | None) -> dict:
    """``profiles/<id>/authorization.yaml``: the only file ever read (ADR-075 d, issue #125).

    ``pid`` None means the only profile; no profile, or several without ``pid``, is a ConfigError. A root
    ``authorization.yaml`` is never read, with or without a profile copy. A missing or unreadable file is a
    ConfigError, so nothing is authorized by accident (ADR-042).
    """
    ids = _profile_folder_ids(root)
    if pid is None:
        if not ids:
            raise ConfigError(f"no profile: expected profiles/<id>/{PROFILE_FILE}")
        if len(ids) > 1:
            raise ConfigError(f"several profiles ({', '.join(ids)}): pass --profile <id> to choose one")
        pid = ids[0]
    rel = f"profiles/{pid}/{AUTH_FILE}"
    path = root / rel
    if not path.is_file():
        raise ConfigError(f"Missing {rel}. Authorization is read from the profile folder only: the root "
                          "copy is not read (ADR-075 d). Nothing was authorized.")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        raise ConfigError(f"{rel} cannot be read. Nothing was authorized.") from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{rel} must be a mapping. Nothing was authorized.")
    return data


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
