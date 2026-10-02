"""CV variants, configured per profile.

A profile keeps its CVs in one folder (``profiles[].cv.dir``), laid out like a
Google Drive folder: one subfolder per variant holding the files, or the files
directly, e.g.

    CV/
      Rui Miranda Resume Tech Lead/
        Rui Miranda Resume Tech Lead.pdf
        Rui Miranda Resume Tech Lead.docx
      Rui Miranda Project Manager/ ...

Names vary, so the variant id is derived: the person's name, words every
variant shares at the start, and "resume"/"cv" are dropped, then slugged
("Rui Miranda Resume Tech Lead" -> ``tech-lead``). ``cv.files`` can map ids to
paths explicitly instead.

The scan runs in the cloud, where those files are not reachable, so the AI
picks from a card per variant kept in the data repo,
``profiles/<id>/cv/<variant>.md`` (what the CV emphasises, which roles it suits).
The card names are the catalog; ``apply run`` (on the owner's machine) turns
the chosen id back into a file.
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path

from .config import ConfigError, data_root, load_config

UPLOADABLE = (".pdf", ".docx", ".doc")      # preference order
NOISE = {"resume", "cv", "curriculum", "vitae"}


def _words(name: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", plain.lower())


def variant_ids(names: list[str], person: str = "") -> dict[str, str]:
    """Map each folder/file stem to a short, stable variant id."""
    split = {n: _words(n) for n in names}
    prefix = 0
    if len(split) > 1:
        lists = list(split.values())
        while all(len(w) > prefix and w[prefix] == lists[0][prefix] for w in lists):
            prefix += 1
    drop = NOISE | set(_words(person))
    out = {}
    for name, words in split.items():
        kept = [w for w in words[prefix:] if w not in drop]
        out[name] = "-".join(kept or words) or "cv"
    return out


def settings(profile: dict) -> dict:
    cv = profile.get("cv") or {}
    return {"dir": cv.get("dir") or "", "default": cv.get("default") or "",
            "files": cv.get("files") or {},
            "text_dir": cv.get("text_dir") or f"profiles/{profile['id']}/cv"}


def _resolve(root: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() or re.match(r"^[A-Za-z]:[\\/]", raw) else root / path


def catalog(root: Path, profile: dict) -> dict[str, Path]:
    """Variant id -> card the AI reads. Empty if the profile has none."""
    text_dir = root / settings(profile)["text_dir"]
    if not text_dir.is_dir():
        return {}
    return {p.stem: p for p in sorted(text_dir.glob("*.md")) if p.stem.lower() != "readme"}


def local_files(root: Path, profile: dict) -> dict[str, Path]:
    """Variant id -> uploadable file, from cv.files and a scan of cv.dir."""
    s = settings(profile)
    found: dict[str, Path] = {}
    base = _resolve(root, s["dir"]) if s["dir"] else None
    if base and base.is_dir():
        entries = {}
        for child in sorted(base.iterdir()):
            if child.is_dir():
                files = [f for ext in UPLOADABLE for f in sorted(child.glob(f"*{ext}"))]
                if files:
                    entries[child.name] = files[0]
            elif child.suffix.lower() in UPLOADABLE:
                entries.setdefault(child.stem, child)
        name = profile.get("display_name") or ""
        ids = variant_ids(list(entries), name)
        for stem, path in entries.items():
            current = found.get(ids[stem])
            rank = UPLOADABLE.index(path.suffix.lower())
            if current is None or rank < UPLOADABLE.index(current.suffix.lower()):
                found[ids[stem]] = path
    for vid, raw in s["files"].items():
        found[vid] = _resolve(root, str(raw))
    return found


def find(files: dict[str, Path], variant: str) -> Path | None:
    """Exact id, else the one id that ends with it ("miranda-tech-lead" ~ "tech-lead")."""
    if variant in files:
        return files[variant]
    hits = [p for vid, p in files.items() if vid.endswith(f"-{variant}")]
    return hits[0] if len(hits) == 1 else None


def profile_by_id(cfg: dict, pid: str | None) -> dict | None:
    return next((p for p in cfg.get("profiles", []) if p.get("id") == pid), None)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="List each profile's CV variants.")
    ap.add_argument("--data")
    args = ap.parse_args(argv)
    try:
        root = data_root(args.data)
        cfg = load_config(root)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    status = 0
    for profile in cfg["profiles"]:
        s, texts, files = settings(profile), catalog(root, profile), local_files(root, profile)
        print(f"{profile['id']}: default={s['default'] or '—'}  dir={s['dir'] or '—'}")
        for vid in sorted(set(texts) | set(files)):
            text = "card ok" if vid in texts else "NO CARD (AI cannot pick it)"
            f = files.get(vid)
            file = (f"file {f}" if f and f.is_file() else
                    "no file here (fine in the cloud)" if not f else f"MISSING {f}")
            print(f"  {vid:24} {text:28} {file}")
        if s["default"] and texts and s["default"] not in texts:
            print(f"  ! default {s['default']!r} has no card in {s['text_dir']}")
            status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
