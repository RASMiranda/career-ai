"""Where a profile's files live in the data repo (ADR-069, ADR-070, ADR-071).

Files that describe one person live under ``profiles/<id>/``, at the same relative name they have
inside the profile folder (``profiles/<id>/apply/triage.yaml``, ``profiles/<id>/cv_manifest.json``).

Phase B (ADR-071) moves the apply-run records (``apply/log.csv``, ``apply/legacy-outcomes.csv``,
``logs/apply/``) the same way. Until the data PR moves them, ``LEGACY`` names their root location and
``resolve`` falls back to it. The new location wins when it exists; a record that exists only at the
root is read and written there, so its history stays in one file; a record that exists nowhere is
created at the profile path. The cleanup PR removes ``LEGACY``.

``applications/``, ``logs/runs.jsonl`` and the failure lines the apply run writes to ``logs/apply/``
stay at the root (ADR-071 (c)).
"""

from pathlib import Path

from .config import PROFILE_FILE, ConfigError

PROFILES = "profiles"

# rel name -> root locations, relative to the data root. Read only while the profile-folder copy does
# not exist. Phase B (ADR-071): remove these entries with the cleanup PR.
LEGACY: dict[str, tuple[str, ...]] = {
    "apply/log.csv": ("apply/log.csv",),
    "apply/legacy-outcomes.csv": ("apply/legacy-outcomes.csv",),
    "logs/apply": ("logs/apply",),
}


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

    For a name in ``LEGACY`` (ADR-071), the profile path wins when it exists; otherwise a root
    location that exists is returned; otherwise the profile path (where a new file is created).
    The path may not exist. ``rel`` must be a relative path with no ``..``. A folder works the same
    way as a file, so ``resolve(root, pid, "logs/apply")`` is the folder to read or write.
    """
    if not pid:
        raise ValueError("a profile id is required to resolve a profile file")
    _check_rel(rel)
    new = Path(root) / PROFILES / pid / rel
    if new.exists():
        return new
    for legacy in LEGACY.get(rel, ()):
        old = Path(root) / legacy
        if old.exists():
            return old
    return new


def apply_path(root, rel: str, pid: str | None = None) -> Path:
    """Where an apply-run record ``rel`` lives for ``pid`` (ADR-071).

    ``pid`` None means the only profile. A data repo with no profile folder at all keeps the root
    location, so a pre-profile data repo and the tests that use one still work. Several profiles
    without ``pid`` is a ConfigError, as for ``default_profile``.
    """
    if pid is None and not profile_ids(root):
        _check_rel(rel)
        return Path(root) / rel
    return resolve(root, pid if pid is not None else default_profile(root), rel)
