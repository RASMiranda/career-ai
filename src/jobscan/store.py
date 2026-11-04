"""Persistence seam: the files a job-scan or apply step keeps go through a Store, never a literal path.

FileStore keeps JSON documents (written atomically) and append-only JSON Lines under one root, which is
the private data repo in production. Names are relative paths inside that root: absolute names, parent
traversal and names that resolve outside the root are refused. Corrupt JSON raises instead of being
replaced by a default, so a later write cannot silently overwrite the evidence.
"""

import json
from pathlib import Path
from typing import Protocol


class Store(Protocol):
    def read_json(self, name: str, default=None): ...
    def write_json(self, name: str, payload) -> None: ...
    def append_line(self, name: str, record: dict) -> None: ...
    def read_lines(self, name: str) -> list[dict]: ...


class FileStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def path(self, name: str) -> Path:
        """The file a name stands for, after checking it stays inside the root."""
        rel = Path(name) if name else Path()
        if not name or rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"store name must be a relative path inside the data repo: {name!r}")
        target = (self.root / rel).resolve()
        if not target.is_relative_to(self.root.resolve()):
            raise ValueError(f"store name escapes the data repo: {name!r}")
        return target

    def read_json(self, name: str, default=None):
        path = self.path(name)
        if not path.is_file():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{name} is not valid JSON; fix or move it before it is overwritten") from exc

    def write_json(self, name: str, payload) -> None:
        path = self.path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)                       # atomic: a crash mid-write never leaves a truncated file

    def append_line(self, name: str, record: dict) -> None:
        path = self.path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:        # never truncates: append-only by construction
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def read_lines(self, name: str) -> list[dict]:
        path = self.path(name)
        if not path.is_file():
            return []
        rows = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{name}:{number} is not valid JSON") from exc
        return rows
