"""CV freshness: are the CV files still the ones the manifest was written for?

``profiles/<id>/cv_manifest.json`` (ADR-069; the data-root and ``state/`` copies are read until the data PR
merges) maps a file's path to the SHA-256 of that file. Paths are relative to the profile folder when the
manifest is there, else to the data repo. A file whose hash differs from the manifest is stale; a listed file that is not there is missing. The
report names the files. It never prints a hash, and never reads a file outside the data repo.
"""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import layout
from .store import FileStore

MANIFEST = "cv_manifest.json"
_SHA256 = re.compile(r"[0-9a-f]{64}")


class CvCheckError(RuntimeError):
    pass


@dataclass
class Report:
    checked: int
    stale: list[str] = field(default_factory=list)      # changed since the manifest was written
    missing: list[str] = field(default_factory=list)    # listed in the manifest but not in the data repo

    @property
    def fresh(self) -> bool:
        return not self.stale and not self.missing


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(root: Path, pid: str | None = None) -> Report:
    """Compare every file the manifest lists with its recorded hash. Raises CvCheckError on a bad manifest.

    The manifest is ``profiles/<pid>/cv_manifest.json`` when it exists there (its keys are then relative to
    that profile folder), else the legacy copy under the data root (keys relative to the data root).
    """
    root = Path(root)
    where = layout.resolve(root, pid, MANIFEST)
    try:
        manifest = FileStore(root).read_json(where.relative_to(root).as_posix(), None)
    except ValueError as exc:
        raise CvCheckError(f"{MANIFEST} is not valid JSON") from exc
    if manifest is None:
        raise CvCheckError(f"no {MANIFEST} in the data repo: nothing to check against")
    if not isinstance(manifest, dict) or not manifest:
        raise CvCheckError(f"{MANIFEST} must map file names to SHA-256 values and list at least one file")

    own_folder = pid is not None and where.parent == root / layout.PROFILES / pid
    store = FileStore(where.parent if own_folder else root)
    report = Report(checked=len(manifest))
    for name in sorted(manifest):
        digest = manifest[name]
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise CvCheckError(f"{MANIFEST}: the value for {name!r} is not a SHA-256 hex digest")
        try:
            path = store.path(name)
        except ValueError as exc:
            raise CvCheckError(f"{MANIFEST}: {name!r} is outside the data repo") from exc
        if not path.is_file():
            report.missing.append(name)
        elif sha256_of(path) != digest:
            report.stale.append(name)
    return report
