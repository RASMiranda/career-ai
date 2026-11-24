"""Where a profile's files live in the data repo (ADR-069, phase A).

Files that describe one person live under ``profiles/<id>/``, at the same relative name they have at
the data root. Until the data PR moves them, the old root location is still read, so code can ship
before the data (ADR-063). A file that exists in neither place is created at the new location.

Phase A moves only the files named in ``LEGACY``. Phase B (apply/log.csv, legacy-outcomes.csv,
logs/apply, logs/runs.jsonl, applications/) keeps its current paths until no run is open.
"""

from pathlib import Path

from .config import PROFILE_FILE, ConfigError

PROFILES = "profiles"

# rel name (as the code asks for it) -> legacy locations, relative to the data root. Read only when the
# profile-folder copy does not exist. cv_manifest.json was read at the root before ADR-069 and the test
# fixtures still write it there, so that location stays in the list too.
LEGACY: dict[str, tuple[str, ...]] = {
    "answer_bank.yaml": ("answer_bank.yaml",),
    "apply/answer-bank.yaml": ("apply/answer-bank.yaml",),
    "apply/triage.yaml": ("apply/triage.yaml",),
    "rate_card.json": ("state/rate_card.json",),
    "cv_manifest.json": ("state/cv_manifest.json", "cv_manifest.json"),
    "OPEN-QUESTIONS.md": ("docs/OPEN-QUESTIONS.md",),
}


def profile_ids(root) -> list[str]:
    """Folder names under profiles/ that hold a profile.yaml, sorted. The folder name is the id."""
    base = Path(root) / PROFILES
    if not base.is_dir():
        return []
    return sorted(p.parent.name for p in base.glob(f"*/{PROFILE_FILE}") if p.is_file())


def default_profile(root, explicit: str | None = None) -> str | None:
    """The profile id a command works on: ``explicit`` if given, else the only profile.

    Returns None when the data repo has no profile folder at all, so the legacy root paths are used.
    Several profiles without an explicit id is an error: the command must be told which one.
    """
    if explicit:
        return explicit
    ids = profile_ids(root)
    if len(ids) > 1:
        raise ConfigError(f"several profiles ({', '.join(ids)}): pass --profile <id> to choose one")
    return ids[0] if ids else None


def resolve(root, pid: str | None, rel: str) -> Path:
    """The path to read or write ``rel`` for profile ``pid``.

    Order: ``profiles/<pid>/<rel>`` if it exists, then each legacy root location that exists, else the
    new path (so a file created now goes to the new location). With no profile, only the legacy
    locations apply, and a missing file resolves to the first of them.
    """
    if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise ValueError(f"layout name must be a relative path inside the data repo: {rel!r}")
    root = Path(root)
    new = root / PROFILES / pid / rel if pid else None
    legacy = [root / name for name in LEGACY.get(rel, ())]
    for path in ([new] if new else []) + legacy:
        if path.is_file():
            return path
    if new:
        return new
    return legacy[0] if legacy else root / rel
