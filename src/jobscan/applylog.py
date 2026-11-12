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
import sys
from datetime import date, timedelta
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


# ---- command line: upsert / outcome / check (ADR-050) ----------------------------------------


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


def upsert(path, *, site, employer, role, job_id, status, when) -> str:
    """Replace the row with this (site, job_id) in place, or append it. Other lines stay byte-identical."""
    row = _build_row(site=site, employer=employer, role=role, job_id=job_id, status=status, when=when)
    p = Path(path)
    raw = p.read_bytes().decode("utf-8") if p.is_file() else ""
    lines = raw.splitlines(keepends=True)
    eol = "\r\n" if any(ln.endswith("\r\n") for ln in lines) else "\n"
    new = _csv_line(row)
    data_idx = [i for i, ln in enumerate(lines) if ln.strip() and not ln.lstrip().startswith("#")]
    if data_idx:
        header = next(csv.reader([lines[data_idx[0]].strip("\r\n")]))
        if tuple(header) != FIELDS:
            raise ApplyLogError(f"{p}: header must be {','.join(FIELDS)}")
        for i in data_idx[1:]:
            cells = next(csv.reader([lines[i].strip("\r\n")]), [])
            if (len(cells) == len(FIELDS) and cells[1].strip().lower() == row["site"].lower()
                    and cells[4].strip() == row["job_id"]):
                tail = lines[i][len(lines[i].rstrip("\r\n")):]
                lines[i] = new + tail
                p.write_bytes("".join(lines).encode("utf-8"))
                return new
    if not data_idx:
        lines.append(",".join(FIELDS) + eol)
    elif lines and not lines[-1].endswith(("\n", "\r")):
        lines[-1] += eol
    lines.append(new + eol)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes("".join(lines).encode("utf-8"))
    return new


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
    c = sub.add_parser("check")
    c.add_argument("--log", required=True)
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
        else:
            print(f"ok, {len(read(a.log))} rows")
    except (ApplyLogError, bank.ApplyOutcomeError, ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
