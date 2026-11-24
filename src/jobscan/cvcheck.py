"""CV freshness: are the CV files still the ones the manifest was written for?

``profiles/<id>/cv_manifest.json`` (ADR-069) maps a file's path, relative to the profile folder, to the
SHA-256 of that file. A file whose hash differs from the manifest is stale; a listed file that is not
there is missing. The report names the files. It never prints a hash, and never reads a file outside
the profile folder.
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


def check(root: Path, pid: str) -> Report:
    """Compare every file the manifest lists with its recorded hash. Raises CvCheckError on a bad manifest.

    The manifest is ``profiles/<pid>/cv_manifest.json``; its keys are relative to that profile folder.
    """
    root = Path(root)
    where = layout.resolve(root, pid, MANIFEST)
    shown = where.relative_to(root).as_posix()
    try:
        manifest = FileStore(root).read_json(shown, None)
    except ValueError as exc:
        raise CvCheckError(f"{MANIFEST} is not valid JSON") from exc
    if manifest is None:
        raise CvCheckError(f"no {shown} in the data repo: nothing to check against")
    if not isinstance(manifest, dict) or not manifest:
        raise CvCheckError(f"{MANIFEST} must map file names to SHA-256 values and list at least one file")

    store = FileStore(where.parent)             # manifest keys resolve inside the profile folder only
    report = Report(checked=len(manifest))
    for name in sorted(manifest):
        digest = manifest[name]
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise CvCheckError(f"{MANIFEST}: the value for {name!r} is not a SHA-256 hex digest")
        try:
            path = store.path(name)
        except ValueError as exc:
            raise CvCheckError(f"{MANIFEST}: {name!r} is outside the profile folder") from exc
        if not path.is_file():
            report.missing.append(name)
        elif sha256_of(path) != digest:
            report.stale.append(name)
    return report
