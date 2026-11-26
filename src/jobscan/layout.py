"""Where a profile's files live in the data repo (ADR-069, ADR-070, ADR-071, ADR-072, ADR-075).

Every file that describes one person lives under ``profiles/<id>/``, at the same relative name it has
inside the profile folder (``profiles/<id>/apply/triage.yaml``, ``profiles/<id>/cv_manifest.json``,
``profiles/<id>/reports/``, ``profiles/<id>/state/``, ``profiles/<id>/applications/queue.json``,
``profiles/<id>/logs/runs.jsonl``, ``profiles/<id>/logs/apply/``). There is no root fallback (ADR-072,
ADR-075 c): a root copy of one of these names is never read or written. A data repo with no profile
folder is a ConfigError, and so are several profiles without an explicit id.
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


def _check_rel(rel: str) -> None:
    if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise ValueError(f"layout name must be a relative path inside the data repo: {rel!r}")


def resolve(root, pid: str, rel: str) -> Path:
    """The path to read or write ``rel`` for profile ``pid``: ``root/profiles/<pid>/<rel>``.

    The path may not exist yet. ``rel`` must be a relative path with no ``..``. A folder works the same
    way as a file, so ``resolve(root, pid, "logs/apply")`` is the folder to read or write.
    """
    if not pid:
        raise ValueError("a profile id is required to resolve a profile file")
    _check_rel(rel)
    return Path(root) / PROFILES / pid / rel


def apply_path(root, rel: str, pid: str | None = None) -> Path:
    """Where a profile file ``rel`` lives for ``pid`` (ADR-071, ADR-072, ADR-075 c).

    ``pid`` None means the only profile. No profile folder, or several profiles without ``pid``, is a
    ConfigError (``default_profile``): a root location is never used.
    """
    return resolve(root, pid if pid is not None else default_profile(root), rel)


def moved_path(root, rel: str, pid: str | None = None) -> Path:
    """Where a phase C file ``rel`` (``state/seen.json``, ``applications/queue.json``) lives: its profile path."""
    return apply_path(root, rel, pid)


def moved_name(root, rel: str, pid: str | None = None) -> str:
    """``moved_path`` as a name relative to the data repo root, for a Store."""
    return moved_path(root, rel, pid).relative_to(Path(root)).as_posix()
