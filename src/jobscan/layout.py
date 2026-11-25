"""Where a profile's files live in the data repo (ADR-069, ADR-070, ADR-071, ADR-072).

Every file that describes one person lives under ``profiles/<id>/``, at the same relative name it has
inside the profile folder (``profiles/<id>/apply/triage.yaml``, ``profiles/<id>/cv_manifest.json``).
That includes the apply-run records (``apply/log.csv``, ``apply/legacy-outcomes.csv``, ``logs/apply/``),
which phase B (ADR-071) moved. There is no root fallback (ADR-072): a root copy of one of these names
is not read or written while the profile folder exists.

``applications/``, ``logs/runs.jsonl`` and the failure lines the apply run writes to the root
``logs/apply/`` stay at the root (ADR-071 (c)). ``apply_path`` keeps that root location for a data repo
with no profile folder at all.
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
    """Where an apply-run record ``rel`` lives for ``pid`` (ADR-071, ADR-072).

    ``pid`` None means the only profile. A data repo with no profile folder at all keeps the root
    location, so a pre-profile data repo and the tests that use one still work. Several profiles
    without ``pid`` is a ConfigError, as for ``default_profile``.
    """
    if pid is None and not profile_ids(root):
        _check_rel(rel)
        return Path(root) / rel
    return resolve(root, pid if pid is not None else default_profile(root), rel)
