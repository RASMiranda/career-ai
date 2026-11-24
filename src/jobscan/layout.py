"""Where a profile's files live in the data repo (ADR-069; ADR-070 removed the root-path fallback).

Files that describe one person live under ``profiles/<id>/``, at the same relative name they have
inside the profile folder (``profiles/<id>/apply/triage.yaml``, ``profiles/<id>/cv_manifest.json``).
There is one location per file: a file that is not there is reported by its profile-folder path.

Phase B paths (the apply log, the apply outcome allowlist, logs/apply, logs/runs.jsonl, applications/)
keep their current paths until no run is open.
"""

from pathlib import Path

from .config import PROFILE_FILE, ConfigError

PROFILES = "profiles"


def profile_ids(root) -> list[str]:
    """Folder names under profiles/ that hold a profile.yaml, sorted. The folder name is the id."""
    base = Path(root) / PROFILES
    if not base.is_dir():
        return []
    return sorted(p.parent.name for p in base.glob(f"*/{PROFILE_FILE}") if p.is_file())


def default_profile(root, explicit: str | None = None) -> str:
    """The profile id a command works on: ``explicit`` if given, else the only profile.

    No profile folder is a ConfigError, and so are several profiles without an explicit id: the
    command must be told which one.
    """
    if explicit:
        return explicit
    ids = profile_ids(root)
    if not ids:
        raise ConfigError(f"no profile: expected {PROFILES}/<id>/{PROFILE_FILE}")
    if len(ids) > 1:
        raise ConfigError(f"several profiles ({', '.join(ids)}): pass --profile <id> to choose one")
    return ids[0]


def resolve(root, pid: str, rel: str) -> Path:
    """The path to read or write ``rel`` for profile ``pid``: ``root/profiles/<pid>/<rel>``.

    The file need not exist. ``rel`` must be a relative path with no ``..``.
    """
    if not pid:
        raise ValueError("a profile id is required to resolve a profile file")
    if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise ValueError(f"layout name must be a relative path inside the data repo: {rel!r}")
    return Path(root) / PROFILES / pid / rel
