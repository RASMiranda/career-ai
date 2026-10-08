"""Clip a job you found yourself into the scan, from a page you saved.

LinkedIn, Indeed, Glassdoor and most company career pages embed the posting as
schema.org ``JobPosting`` JSON-LD (Google for Jobs requires it). This reads that from
an HTML file on your disk (browser: Save Page As), so it needs no selectors, no login
and no network, and cannot get an account restricted:

    python -m jobscan.clip page.html [page2.html …] --data D [--profile ID] [--url LINK]

Each posting goes into ``<data>/inbox/clips.json``. The next scan collects it like any
other source: seen-set, blacklist and prefilter apply, then the model scores it. Commit
``inbox/`` in career-data so the cloud routine can see it. It warns now if the
prefilter would discard the job.

The page is untrusted text. It is parsed as data (``json.loads``), never run, and the
description reaches the model like any other posting.
"""

import argparse
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

from .config import ConfigError, data_root, load_config
from .models import Candidate
from .normalize import candidate_key, is_http_url, truncate
from .state import Seen, _read, _write
from . import triage

SOURCE = "clip"
MAX_FILE_BYTES = 5_000_000
MAX_PER_FILE = 25
MIN_DESCRIPTION = 40
DESCRIPTION_CHARS = 2500

_LD = re.compile(r"<script\b[^>]*\btype\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.I | re.S)
_CANONICAL = re.compile(r"<link\b[^>]*\brel\s*=\s*[\"']canonical[\"'][^>]*>", re.I)
_OG_URL = re.compile(r"<meta\b[^>]*\bproperty\s*=\s*[\"']og:url[\"'][^>]*>", re.I)
_HREF = re.compile(r"\b(?:href|content)\s*=\s*[\"']([^\"']+)[\"']", re.I)


class ClipError(RuntimeError):
    pass


def _walk(node):
    """Every dict inside parsed JSON-LD, including @graph and lists."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _is_job(node: dict) -> bool:
    kind = node.get("@type")
    return "JobPosting" in kind if isinstance(kind, list) else kind == "JobPosting"


def _text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return _text(value.get("name") or value.get("value") or "")
    if isinstance(value, list):
        return ", ".join(t for t in (_text(v) for v in value) if t)
    return ""


def _location(job: dict) -> str:
    places = job.get("jobLocation")
    places = places if isinstance(places, list) else [places] if places else []
    names = []
    for place in places:
        addr = place.get("address") if isinstance(place, dict) else None
        if isinstance(addr, dict):
            parts = [_text(addr.get(k)) for k in ("addressLocality", "addressRegion", "addressCountry")]
            names.append(", ".join(p for p in parts if p))
        else:
            names.append(_text(addr or place))
    return "; ".join(n for n in names if n)


def _salary(job: dict) -> str:
    """Only what the posting states. Absent stays absent."""
    pay = job.get("baseSalary")
    if not isinstance(pay, dict):
        return ""
    value = pay.get("value") if isinstance(pay.get("value"), dict) else pay
    low, high, single = value.get("minValue"), value.get("maxValue"), value.get("value")
    present = lambda v: v not in (None, "") and not isinstance(v, (dict, list))  # noqa: E731
    if present(low) and present(high):
        amount = f"{low}-{high}"
    elif present(low) or present(high):
        amount = str(low if present(low) else high)
    elif present(single):
        amount = str(single)
    else:
        return ""
    return " ".join(p for p in (_text(pay.get("currency")), amount, _text(value.get("unitText"))) if p)


def _page_url(page: str) -> str:
    for rx in (_CANONICAL, _OG_URL):
        tag = rx.search(page)
        found = _HREF.search(tag.group(0)) if tag else None
        if found and is_http_url(html.unescape(found.group(1))):
            return html.unescape(found.group(1))
    return ""


def parse(page: str, profile: str, url: str = "") -> list[Candidate]:
    """Every JobPosting in the page as a Candidate. Raises ClipError if there is none usable."""
    jobs = []
    for block in _LD.findall(page):
        data = None
        for text in (block, html.unescape(block)):          # some pages entity-encode the JSON
            try:
                data = json.loads(text)
                break
            except json.JSONDecodeError:
                continue
        jobs += [n for n in _walk(data) if _is_job(n)]
    if not jobs:
        raise ClipError("no schema.org JobPosting found in this page")
    fallback = _page_url(page)
    out, problems = [], []
    for job in jobs[:MAX_PER_FILE]:
        title, company = _text(job.get("title") or job.get("name")), _text(job.get("hiringOrganization"))
        # Descriptions are HTML, often escaped twice: decode first, then strip tags.
        description = triage.clean(html.unescape(_text(job.get("description"))))
        link = url or _text(job.get("url")) or fallback
        remote = True if _text(job.get("jobLocationType")).upper() == "TELECOMMUTE" else None
        source_id = _text(job.get("identifier"))
        if not title or not company:
            problems.append("a posting has no title or no hiring organisation")
        elif not is_http_url(link):
            problems.append(f"{title}: no http(s) link; pass --url")
        elif len(description) < MIN_DESCRIPTION:
            problems.append(f"{title}: no usable description")
        else:
            out.append(Candidate(
                candidate_key=candidate_key(SOURCE, source_id, title, company), profile=profile,
                source=SOURCE, title=title, company=company, location=_location(job), remote=remote,
                contract_type=_text(job.get("employmentType")), salary=_salary(job),
                description=truncate(description, DESCRIPTION_CHARS), url=link,
                posted_at=_text(job.get("datePosted")), source_id=source_id))
    if not out:
        raise ClipError("; ".join(problems))
    return out


# ----------------------------------------------------------------------- inbox
def inbox_path(root: Path) -> Path:
    return root / "inbox" / "clips.json"


def pending(root: Path, seen: Seen) -> list[tuple[str, Candidate]]:
    """(profile id, candidate) for every clip the scan has not seen yet."""
    fields = set(Candidate.__dataclass_fields__)
    out = []
    for entry in _read(inbox_path(root), {}).get("clips", []):
        cand = entry.get("candidate") or {}
        if entry.get("profile") and cand.get("candidate_key") and cand["candidate_key"] not in seen:
            out.append((entry["profile"], Candidate(**{k: v for k, v in cand.items() if k in fields})))
    return out


def add(root: Path, seen: Seen, candidates: list[Candidate]) -> tuple[list[Candidate], list[Candidate]]:
    """Store new clips; returns (added, already known). Entries the scan has seen are dropped."""
    store = _read(inbox_path(root), {})
    clips = [c for c in store.get("clips", []) if c.get("candidate", {}).get("candidate_key") not in seen]
    have = {c["candidate"]["candidate_key"] for c in clips}
    added, known = [], []
    for cand in candidates:
        if cand.candidate_key in have or cand.candidate_key in seen:
            known.append(cand)
            continue
        clips.append({"profile": cand.profile, "clipped_on": date.today().isoformat(),
                      "candidate": cand.to_dict()})
        have.add(cand.candidate_key)
        added.append(cand)
    _write(inbox_path(root), {"clips": clips})
    return added, known


# ------------------------------------------------------------------------- cli
def _profile_id(cfg: dict, wanted: str | None) -> str:
    ids = [p["id"] for p in cfg["profiles"]]
    if wanted:
        if wanted not in ids:
            raise ClipError(f"unknown profile {wanted!r}; profiles: {', '.join(ids)}")
        return wanted
    if len(ids) != 1:
        raise ClipError(f"which profile? pass --profile ({', '.join(ids)})")
    return ids[0]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jobscan.clip", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="HTML pages you saved from your browser")
    ap.add_argument("--data")
    ap.add_argument("--profile")
    ap.add_argument("--url", help="the link you would apply from (default: the page's own)")
    args = ap.parse_args(argv)
    try:
        root = data_root(args.data)
        cfg = load_config(root)
        pid = _profile_id(cfg, args.profile)
        profile = next(p for p in cfg["profiles"] if p["id"] == pid)
        rules = triage.rules_for(profile)
    except (ConfigError, ClipError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.url and len(args.files) > 1:
        print("error: --url names one job; clip one file at a time with it", file=sys.stderr)
        return 2

    status, found = 0, []
    for name in args.files:
        path = Path(name)
        try:
            if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                raise ClipError("not a file, or larger than 5 MB")
            found += parse(path.read_text(encoding="utf-8", errors="replace"), pid, args.url or "")
        except (ClipError, OSError) as exc:
            print(f"  {path.name}: {exc}", file=sys.stderr)
            status = 1
    added, known = add(root, Seen(root), found)
    for cand in added:
        why = triage.reject_reason(cand.to_dict(), rules)
        print(f"  clipped  {cand.title} — {cand.company}" + (f"\n    ! the prefilter will discard it: {why}" if why else ""))
    for cand in known:
        print(f"  already known  {cand.title} — {cand.company}")
    if added:
        print(f"{len(added)} added to inbox/clips.json. Commit inbox/ in career-data; the next scan scores it.")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
