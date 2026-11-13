"""Application log for the browser-apply runs: one CSV row per job considered.

Lives in career-data as ``apply/log.csv``. Columns: date, site, employer, role, job_id, status.
Lines starting with ``#`` are comments (TODO notes): kept on disk, skipped on read.
Dates are ISO (YYYY-MM-DD). A blank date means unknown; for ``employer_applied_recently`` an
unknown date counts as recent, so an employer is not applied to twice by accident.

Duplicate rule: ``is_duplicate`` matches any status, so a job already seen (even SKIPPED) is not
re-staged. Only the APPLIED statuses count toward ``employer_applied_recently``.
"""

import argparse
import csv
import io
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from .blacklist import canon

FIELDS = ("date", "site", "employer", "role", "job_id", "status")
# Single source of truth for apply statuses (ADR-049). ``bank.STATUSES`` (the jsonl outcome record)
# is this whole tuple; ``apply/log.csv`` accepts the same minus the two record-only states.
APPLY_STATUSES = ("CANDIDATE", "STAGED", "SUBMITTED", "UNCONFIRMED", "SKIPPED", "BLOCKED", "CLOSED",
                  "ALREADY_APPLIED")
STATUSES = tuple(s for s in APPLY_STATUSES if s not in ("STAGED", "CLOSED"))  # what log.csv accepts
APPLIED = ("SUBMITTED", "UNCONFIRMED", "ALREADY_APPLIED")


class ApplyLogError(ValueError):
    pass


def _data_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def read(path) -> list[dict]:
    """All rows, oldest first. A missing or empty file is an empty log."""
    p = Path(path)
    if not p.is_file():
        return []
    lines = _data_lines(p.read_text(encoding="utf-8"))
    if not lines:
        return []
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    if tuple(reader.fieldnames or ()) != FIELDS:
        raise ApplyLogError(f"{p}: header must be {','.join(FIELDS)}")
    rows = []
    for n, row in enumerate(reader, start=1):
        clean = {k: (row.get(k) or "").strip() for k in FIELDS}
        if clean["status"] not in STATUSES:
            raise ApplyLogError(f"{p}: row {n}: unknown status {clean['status']!r}")
        rows.append(clean)
    return rows


def append(path, *, site: str, employer: str, role: str, job_id: str, status: str,
           when: str | None = None) -> dict:
    """Add one row. ``when`` is an ISO date (default today). Writes the header on first use."""
    if status not in STATUSES:
        raise ApplyLogError(f"unknown status {status!r}; one of {', '.join(STATUSES)}")
    if not str(site).strip() or not str(job_id).strip():
        raise ApplyLogError("site and job_id are required")
    stamp = when if when is not None else date.today().isoformat()
    if stamp:
        try:
            date.fromisoformat(stamp)
        except ValueError:
            raise ApplyLogError(f"date {stamp!r} must be ISO (YYYY-MM-DD) or blank")
    row = {"date": stamp, "site": str(site).strip(), "employer": str(employer).strip(),
           "role": str(role).strip(), "job_id": str(job_id).strip(), "status": status}

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = p.read_text(encoding="utf-8") if p.is_file() else ""
    needs_header = not _data_lines(text)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    if needs_header:
        writer.writeheader()
    writer.writerow(row)
    separator = "\n" if text and not text.endswith("\n") else ""
    p.write_text(text + separator + buf.getvalue(), encoding="utf-8")
    return row


def is_duplicate(path, site: str, job_id: str) -> bool:
    """True when this site and job ID already have a row, whatever its status."""
    s, j = str(site).strip().lower(), str(job_id).strip()
    return any(r["site"].lower() == s and r["job_id"] == j for r in read(path))


def employer_applied_recently(path, employer: str, days: int = 180, today: date | None = None) -> bool:
    """True when an APPLIED row for this employer is dated within ``days`` (blank date counts)."""
    name = canon(employer)
    if not name:
        return False
    cutoff = (today or date.today()) - timedelta(days=days)
    for r in read(path):
        if r["status"] not in APPLIED or canon(r["employer"]) != name:
            continue
        if not r["date"]:
            return True
        try:
            when = date.fromisoformat(r["date"])
        except ValueError:
            raise ApplyLogError(f"bad date {r['date']!r} for {r['employer']!r}")
        if when >= cutoff:
            return True
    return False


# ---- command line: upsert / outcome / check / batch (ADR-050, ADR-053) ------------------------

# Rows file for ``batch``: the log columns plus the outcome fields (ADR-053).
ROWS_FIELDS = ("date", "site", "employer", "role", "job_id", "status", "verified_by", "ts")
# Government ID shapes (ADR-049(c)): a formatted CPF, or a label followed by 6+ digits.
_ID_SHAPE = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")
_ID_LABEL = re.compile(r"(?i)(?:cpf|documento|passport|tax\s*id|ssn)\W{0,3}\d{6,}")


def _csv_line(row: dict) -> str:
    buf = io.StringIO()
    csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="").writerow(row)
    return buf.getvalue()


def _build_row(*, site, employer, role, job_id, status, when) -> dict:
    from .bank import _SITE  # lazy: bank imports this module
    if status not in STATUSES:
        raise ApplyLogError(f"unknown status {status!r}; one of {', '.join(STATUSES)}")
    if not str(site).strip() or not str(job_id).strip():
        raise ApplyLogError("site and job_id are required")
    if not _SITE.fullmatch(str(site).strip()):
        raise ApplyLogError(f"site {site!r} must be a lowercase slug such as greenhouse")
    try:
        date.fromisoformat(when)
    except ValueError:
        raise ApplyLogError(f"date {when!r} must be ISO (YYYY-MM-DD)")
    return {"date": when, "site": str(site).strip(), "employer": str(employer).strip(),
            "role": str(role).strip(), "job_id": str(job_id).strip(), "status": status}


def _apply_row_text(raw: str, row: dict) -> tuple[str, str]:
    """Put ``row`` into the log text. Returns (new text, "new" | "updated" | "unchanged").

    The row replaces the line with the same (site, job_id); every other line stays byte-identical.
    """
    lines = raw.splitlines(keepends=True)
    eol = "\r\n" if any(ln.endswith("\r\n") for ln in lines) else "\n"
    new = _csv_line(row)
    data_idx = [i for i, ln in enumerate(lines) if ln.strip() and not ln.lstrip().startswith("#")]
    if data_idx:
        header = next(csv.reader([lines[data_idx[0]].strip("\r\n")]))
        if tuple(header) != FIELDS:
            raise ApplyLogError(f"header must be {','.join(FIELDS)}")
        for i in data_idx[1:]:
            cells = next(csv.reader([lines[i].strip("\r\n")]), [])
            if (len(cells) == len(FIELDS) and cells[1].strip().lower() == row["site"].lower()
                    and cells[4].strip() == row["job_id"]):
                tail = lines[i][len(lines[i].rstrip("\r\n")):]
                if lines[i] == new + tail:
                    return raw, "unchanged"
                lines[i] = new + tail
                return "".join(lines), "updated"
    if not data_idx:
        lines.append(",".join(FIELDS) + eol)
    elif lines and not lines[-1].endswith(("\n", "\r")):
        lines[-1] += eol
    lines.append(new + eol)
    return "".join(lines), "new"


def upsert(path, *, site, employer, role, job_id, status, when) -> str:
    """Replace the row with this (site, job_id) in place, or append it. Other lines stay byte-identical."""
    row = _build_row(site=site, employer=employer, role=role, job_id=job_id, status=status, when=when)
    p = Path(path)
    raw = p.read_bytes().decode("utf-8") if p.is_file() else ""
    text, action = _apply_row_text(raw, row)
    if action != "unchanged":
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8"))
    return _csv_line(row)


def _id_problems(text: str, name: str) -> list[str]:
    """Lines that look like a government ID number. Names the place, never the matched value."""
    return [f"{name}:{n}: looks like a government ID number; remove it (value not shown)"
            for n, line in enumerate(text.splitlines(), start=1)
            if _ID_SHAPE.search(line) or _ID_LABEL.search(line)]


def _outcome_keys(root: Path) -> tuple[set, list[str]]:
    """(site, job_id) pairs with a jsonl outcome under logs/apply, and any problems in those files."""
    keys, problems = set(), []
    folder = root / "logs" / "apply"
    for f in sorted(folder.glob("*.jsonl")) if folder.is_dir() else []:
        text = f.read_text(encoding="utf-8")
        problems += _id_problems(text, str(f))
        for n, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                problems.append(f"{f}:{n}: not valid JSON")
                continue
            if isinstance(rec, dict):
                keys.add((str(rec.get("site", "")), str(rec.get("job_id", ""))))
    return keys, problems


LEGACY_FIELDS = ("site", "job_id", "reason")
LEGACY_FILE = Path("apply") / "legacy-outcomes.csv"  # under the data folder (ADR-054)


def _legacy_allowlist(root: Path) -> dict[tuple[str, str], int]:
    """(site, job_id) -> line number from apply/legacy-outcomes.csv. A missing file is an empty list."""
    p = root / LEGACY_FILE
    if not p.is_file():
        return {}
    numbered = [(n, ln) for n, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1)
                if ln.strip() and not ln.lstrip().startswith("#")]
    if not numbered or tuple(h.strip() for h in next(csv.reader([numbered[0][1]]))) != LEGACY_FIELDS:
        raise ApplyLogError(f"{p}: header must be {','.join(LEGACY_FIELDS)}")
    out: dict[tuple[str, str], int] = {}
    for n, ln in numbered[1:]:
        cells = next(csv.reader([ln]), [])
        if len(cells) != len(LEGACY_FIELDS):
            raise ApplyLogError(f"{p}:{n}: expected {len(LEGACY_FIELDS)} fields")
        site, job_id, reason = (c.strip() for c in cells)
        if not site or not job_id or not reason:
            raise ApplyLogError(f"{p}:{n}: site, job_id and reason are all required")
        key = (site, job_id)
        if key in out:
            raise ApplyLogError(f"{p}:{n}: duplicate entry (first at line {out[key]})")
        out[key] = n
    return out


def check_log(log, data=None):
    """Validate apply/log.csv and, given ``data``, the jsonl outcomes.

    Returns (errors, gaps, warnings, rows, legacy). A structural error in the CSV raises ApplyLogError,
    as ``read`` does. ``gaps``: SUBMITTED rows with no outcome and not on the legacy allowlist; these
    fail --strict. ``legacy``: distinct allowlisted SUBMITTED rows with no outcome. ``warnings``: stale
    allowlist entries; they never fail. A job ID is echoed only when it is in the log.
    """
    p = Path(log)
    rows = read(p)
    text = p.read_text(encoding="utf-8") if p.is_file() else ""
    errors = _id_problems(text, str(p))
    gaps, warnings, legacy_keys = [], [], set()
    if data is not None:
        root = Path(data)
        if not root.is_dir():
            raise ApplyLogError(f"data folder not found: {root}")
        keys, outcome_problems = _outcome_keys(root)
        errors += outcome_problems
        allow = _legacy_allowlist(root)
        allow_path = root / LEGACY_FILE
        if allow_path.is_file():
            errors += _id_problems(allow_path.read_text(encoding="utf-8"), str(allow_path))
        submitted = {(r["site"], r["job_id"]) for r in rows if r["status"] == "SUBMITTED"}
        for r in rows:
            key = (r["site"], r["job_id"])
            if r["status"] != "SUBMITTED" or key in keys:
                continue
            if key in allow:
                legacy_keys.add(key)
            else:
                gaps.append(f"no outcome for {r['site']} {r['job_id']}")
        for key, line in allow.items():
            if key in submitted and key in keys:
                warnings.append(f"legacy entry has an outcome: {key[0]} {key[1]}")
            elif key not in submitted:
                # no echo: this job ID is not in the log
                warnings.append(f"legacy entry at line {line} has no SUBMITTED row in the log")
    return errors, gaps, warnings, len(rows), len(legacy_keys)


def read_rows(path) -> list[tuple[int, dict]]:
    """Rows of a batch file as (row number, fields). Row numbers count data rows from 1."""
    p = Path(path)
    if not p.is_file():
        raise ApplyLogError(f"{p}: rows file not found")
    lines = _data_lines(p.read_text(encoding="utf-8"))
    if not lines:
        return []
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    if tuple(reader.fieldnames or ()) != ROWS_FIELDS:
        raise ApplyLogError(f"{p}: header must be {','.join(ROWS_FIELDS)}")
    out = []
    for n, raw in enumerate(reader, start=1):
        if None in raw:
            raise ApplyLogError(f"row {n}: more cells than the header")
        out.append((n, {k: (raw.get(k) or "").strip() for k in ROWS_FIELDS}))
    return out


def _batch_outcome(n: int, r: dict, seen: set):
    """Validate one rows-file row. Returns the outcome record to write, or None when there is none."""
    from . import bank

    def fail(msg: str):
        raise ApplyLogError(f"row {n}: {msg}")

    for f in ("date", "site", "job_id", "status", "ts"):
        if not r[f]:
            fail(f"{f} is required")
    if r["status"] not in STATUSES:
        fail(f"unknown status {r['status']!r}; one of {', '.join(STATUSES)}")
    if r["verified_by"] and r["verified_by"] not in bank.VERIFIED_BY:
        fail(f"verified_by must be one of {', '.join(bank.VERIFIED_BY)}, or blank")
    if r["status"] == "SUBMITTED" and not r["verified_by"]:
        fail("a SUBMITTED row must say how it was verified (verified_by)")
    if r["status"] == "ALREADY_APPLIED" and r["verified_by"] not in ("site_applied_list", "human"):
        fail("an ALREADY_APPLIED row must be verified by site_applied_list or human")
    if not bank._SITE.fullmatch(r["site"]):
        fail(f"site {r['site']!r} must be a lowercase slug such as greenhouse")
    try:
        date.fromisoformat(r["date"])
    except ValueError:
        fail(f"date {r['date']!r} must be ISO (YYYY-MM-DD)")
    try:
        datetime.fromisoformat(r["ts"])
    except ValueError:
        fail(f"ts {r['ts']!r} must be ISO")
    key = (r["site"], r["job_id"])
    if key in seen:
        fail(f"site and job_id {r['site']} {r['job_id']} appear twice in the file")
    seen.add(key)
    if not (r["verified_by"] or r["status"] in ("SUBMITTED", "ALREADY_APPLIED")):
        return None
    outcome = bank.ApplyOutcome(job_id=r["job_id"], employer=r["employer"], role=r["role"],
                                site=r["site"], status=r["status"], verified_by=r["verified_by"],
                                ts=r["ts"])
    try:
        return bank.validate_outcome(outcome)
    except bank.ApplyOutcomeError as e:
        fail(str(e))


def batch(log, data, rows_file) -> dict:
    """Validate every row first, then write the log rows and jsonl outcomes. All or nothing.

    Idempotent: a row already in the log is left alone, and an outcome line already on disk is not
    written twice. Returns counts: new, updated, unchanged, outcomes (lines written).
    """
    from dataclasses import asdict
    from . import bank
    from .config import data_root

    rows = read_rows(rows_file)
    seen: set = set()
    plan = [(n, r, _batch_outcome(n, r, seen)) for n, r in rows]

    p = Path(log)
    raw = p.read_bytes().decode("utf-8") if p.is_file() else ""
    counts = {"new": 0, "updated": 0, "unchanged": 0}
    text = raw
    for _n, r, _outcome in plan:
        row = _build_row(site=r["site"], employer=r["employer"], role=r["role"], job_id=r["job_id"],
                         status=r["status"], when=r["date"])
        text, action = _apply_row_text(text, row)
        counts[action] += 1

    root = data_root(data)
    problems = _id_problems(text, str(p))
    outcome_writes = []  # (path, line) still to be written
    for _n, _r, outcome in plan:
        if outcome is None:
            continue
        clean = bank.ApplyOutcome(**{k: bank.redact(v) for k, v in asdict(outcome).items()})
        line = json.dumps(asdict(clean), sort_keys=True, ensure_ascii=False)
        target = bank.outcome_path(root, clean.site, clean.ts)
        have = target.read_text(encoding="utf-8").splitlines() if target.is_file() else []
        problems += _id_problems(line, str(target))
        if line not in have:
            outcome_writes.append((target, line))
    if problems:
        raise ApplyLogError("; ".join(problems))

    for target, line in outcome_writes:
        target.parent.mkdir(parents=True, exist_ok=True)
        lead = ""
        if target.is_file() and target.read_bytes()[-1:] not in (b"", b"\n"):
            lead = "\n"
        with target.open("a", encoding="utf-8") as fh:
            fh.write(lead + line + "\n")
    if text != raw:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8"))
    return {**counts, "outcomes": len(outcome_writes)}


def _check(log, data, strict: bool) -> int:
    errors, gaps, warnings, rows, legacy = check_log(log, data)
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        return 2
    for g in gaps:
        print(f"warning: {g}")
    for w in warnings:
        print(f"warning: {w}")
    if data is not None:
        print(f"legacy: {legacy}")
    if strict and gaps:
        print(f"error: --strict: {len(gaps)} SUBMITTED row(s) without an outcome", file=sys.stderr)
        return 2
    print(f"ok, {rows} rows")
    return 0


def main(argv=None) -> int:
    from . import bank
    ap = argparse.ArgumentParser(prog="python -m jobscan.applylog")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("upsert", "outcome"):
        q = sub.add_parser(name)
        if name == "upsert":
            q.add_argument("--log", required=True)
            q.add_argument("--date", required=True)
        else:
            q.add_argument("--data", required=True)
            q.add_argument("--ts", required=True)
            q.add_argument("--verified-by", default="", choices=["", *bank.VERIFIED_BY])
        for f in ("site", "employer", "role", "job-id", "status"):
            q.add_argument("--" + f, required=True)
    b = sub.add_parser("batch", help="validate a rows file, then write its log rows and outcomes")
    b.add_argument("--log", required=True)
    b.add_argument("--data", required=True)
    b.add_argument("--file", required=True)
    c = sub.add_parser("check")
    c.add_argument("--log", required=True)
    c.add_argument("--data", help="also check that every SUBMITTED row has a jsonl outcome")
    c.add_argument("--strict", action="store_true", help="exit 2 when a SUBMITTED row has no outcome")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "upsert":
            print(upsert(a.log, site=a.site, employer=a.employer, role=a.role, job_id=a.job_id,
                         status=a.status, when=a.date))
        elif a.cmd == "outcome":
            path = bank.append_outcome(bank.ApplyOutcome(
                job_id=a.job_id, employer=a.employer, role=a.role, site=a.site, status=a.status,
                verified_by=a.verified_by, ts=a.ts), data=a.data)
            print(path)
        elif a.cmd == "batch":
            counts = batch(a.log, a.data, a.file)
            print(f"{counts['new']} new, {counts['updated']} updated, {counts['unchanged']} unchanged")
            print(f"outcomes: {counts['outcomes']} written")
            return _check(a.log, a.data, strict=False)
        else:
            return _check(a.log, a.data, a.strict)
    except (ApplyLogError, bank.ApplyOutcomeError, ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
