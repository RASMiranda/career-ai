"""Where a profile's files live in the data repo (ADR-069, ADR-070, ADR-071, ADR-072).

Every file that describes one person lives under ``profiles/<id>/``, at the same relative name it has
inside the profile folder (``profiles/<id>/apply/triage.yaml``, ``profiles/<id>/cv_manifest.json``).
That includes the apply-run records (``apply/log.csv``, ``apply/legacy-outcomes.csv``, ``logs/apply/``),
which phase B (ADR-071) moved. There is no root fallback (ADR-072): a root copy of one of these names
is not read or written while the profile folder exists.

``apply_path`` keeps the root location for a data repo with no profile folder at all.

Phase C (issue #118) moves ``reports/``, ``state/``, ``applications/`` (``queue.json``, ``answers.json``)
and ``logs/runs.jsonl`` under the profile too. Until the data repo has been renamed, ``moved_path``
resolves them with a LEGACY rule, at folder level so the files of one folder never split: the profile
path wins when it exists; otherwise an existing root folder (or file, for ``logs/runs.jsonl``) is read
AND written in place, new files included, with one warning; otherwise the profile path is created. The
cleanup PR deletes this fallback. The ``logs/apply/`` failure lines are not here: they follow the
profile of the failed job.
"""

import sys
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
    """Where an apply-run record ``rel`` lives for ``pid`` (ADR-071, ADR-072).

    ``pid`` None means the only profile. A data repo with no profile folder at all keeps the root
    location, so a pre-profile data repo and the tests that use one still work. Several profiles
    without ``pid`` is a ConfigError, as for ``default_profile``.
    """
    if pid is None and not profile_ids(root):
        _check_rel(rel)
        return Path(root) / rel
    return resolve(root, pid if pid is not None else default_profile(root), rel)


# --- LEGACY (phase C): removed by the cleanup PR together with the root allowlist entries.
MOVED_FOLDERS = ("reports", "state", "applications")
MOVED_FILES = ("logs/runs.jsonl",)
_warned: set[tuple[str, str]] = set()


def _legacy_unit(rel: str) -> str | None:
    """The folder or file that moves as one unit and holds ``rel``, or None when ``rel`` is not moved."""
    _check_rel(rel)
    if rel in MOVED_FILES:
        return rel
    first = Path(rel).parts[0]
    return first if first in MOVED_FOLDERS else None


def moved_path(root, rel: str, pid: str | None = None) -> Path:
    """Where a phase C file ``rel`` (``state/seen.json``, ``applications/queue.json``) lives, LEGACY rule above.

    No profile folder at all keeps the root, as ``apply_path``. Several profiles without ``pid`` use the
    root only while it still holds the data, else a ConfigError. A name that does not move is resolved
    like ``apply_path``.
    """
    unit = _legacy_unit(rel)
    if unit is None:
        return apply_path(root, rel, pid)
    root_path, ids = Path(root) / unit, profile_ids(root)
    if not ids:
        return Path(root) / rel
    if pid is None:
        if len(ids) > 1:
            if root_path.exists():
                return Path(root) / rel
            raise ConfigError(f"several profiles ({', '.join(ids)}): pass --profile <id> to choose one")
        pid = ids[0]
    if resolve(root, pid, unit).exists() or not root_path.exists():
        return resolve(root, pid, rel)
    if (str(root), unit) not in _warned:
        _warned.add((str(root), unit))
        print(f"warning: {unit} is still at the data repo root (LEGACY); it moves to "
              f"{PROFILES}/{pid}/{unit} in the data repo rename", file=sys.stderr)
    return Path(root) / rel


def moved_name(root, rel: str, pid: str | None = None) -> str:
    """``moved_path`` as a name relative to the data repo root, for a Store."""
    return moved_path(root, rel, pid).relative_to(Path(root)).as_posix()
