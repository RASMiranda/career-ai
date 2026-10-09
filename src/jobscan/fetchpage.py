"""Fetch a few public pages for a test or a fixture, politely, and stop at the first sign of a block.

    python -m jobscan.fetchpage URL [URL …] --out-dir DIR

For a development session the owner asked to test `jobscan.clip` or to build a site parser from real
pages (docs/CAPTURING-PAGES.md, ADR-021). It is not a crawler and not part of the scan:

- one plain GET per URL, logged out, no cookies, no login, no retries, honest User-Agent
- at most 5 URLs per run, a pause between them, public https hosts only
- the first block signal ends the run and the host for the day: HTTP 401/403/429/451/999, a redirect
  to a login or challenge page, a CAPTCHA or "unusual activity" page. Nothing is tried to get past it
  (no other User-Agent, no proxy, no headless trick): the answer is to save the page in your own browser

Each saved page is checked with `jobscan.clip` straight away, so the result of the test is on screen.
"""

import argparse
import hashlib
import ipaddress
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from . import __version__, clip

UA = f"career-ai-jobscan/{__version__} (+one page, fetched at the owner's request)"
MAX_URLS = 5
MAX_BYTES = 5_000_000
MAX_REDIRECTS = 3
DELAY_SECONDS = 5
BLOCK_STATUS = {401, 403, 407, 429, 451, 999}
_BLOCK_PATH = re.compile(r"authwall|/login|/signin|/sign-in|/uas/|checkpoint|captcha|challenge|/m/login", re.I)
_BLOCK_TEXT = ("g-recaptcha", "h-captcha", "cf-turnstile", "unusual traffic", "unusual activity",
               "verify you are a human", "verify you are human", "are you a robot", "request blocked")
_BLOCK_TITLE = re.compile(r"<title>\s*(just a moment|attention required|access denied)", re.I)
BLOCKS_FILE = ".fetch-blocks.json"


class Blocked(RuntimeError):
    pass


class Refused(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def refuse_reason(url: str, allow_local: bool = False) -> str:
    """Why this URL may not be fetched, or '' when it may."""
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" and not (allow_local and parts.scheme == "http"):
        return "only https URLs"
    if not host:
        return "no host"
    if allow_local:
        return ""
    if host == "localhost" or host.endswith((".local", ".internal", ".localhost", ".svc.cluster.local")):
        return "not a public host"
    try:
        if not ipaddress.ip_address(host).is_global:
            return "not a public address"
    except ValueError:
        pass
    return ""


def block_reason(status: int, url: str, body: str) -> str:
    """The reason this response is a block signal, or '' when it is a normal page."""
    if status in BLOCK_STATUS:
        return f"HTTP {status}"
    if _BLOCK_PATH.search(urllib.parse.urlsplit(url).path):
        return f"redirected to a login or challenge page ({urllib.parse.urlsplit(url).path[:40]})"
    low = body[:300_000].lower()
    for marker in _BLOCK_TEXT:
        if marker in low:
            return f"the page asks for a CAPTCHA or reports unusual activity ({marker})"
    if _BLOCK_TITLE.search(body[:5000]):
        return "a challenge page"
    return ""


def _get(url: str, timeout: int) -> tuple[int, str, str]:
    """One GET, redirects followed by hand so each hop can be judged. Returns (status, final url, body)."""
    opener = urllib.request.build_opener(_NoRedirect)           # no cookie jar: every fetch is logged out
    for _ in range(MAX_REDIRECTS + 1):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
        try:
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read(MAX_BYTES + 1)
                status = resp.status
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308) and exc.headers.get("Location"):
                url = urllib.parse.urljoin(url, exc.headers["Location"])
                if block_reason(200, url, ""):
                    return exc.code, url, ""
                continue
            return exc.code, url, ""
        if len(raw) > MAX_BYTES:
            raise Refused(f"larger than {MAX_BYTES // 1_000_000} MB")
        return status, url, raw.decode("utf-8", "replace")
    raise Refused(f"more than {MAX_REDIRECTS} redirects")


def _blocks(out_dir: Path) -> dict:
    try:
        return json.loads((out_dir / BLOCKS_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _record_block(out_dir: Path, host: str) -> None:
    data = _blocks(out_dir)
    data[host] = date.today().isoformat()
    (out_dir / BLOCKS_FILE).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _name(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    slug = re.sub(r"[^a-z0-9]+", "-", (parts.hostname or "x") + parts.path.lower()).strip("-")[:48].strip("-")
    return f"{slug}-{hashlib.sha1(url.encode()).hexdigest()[:6]}.html"


def fetch_all(urls: list[str], out_dir: Path, *, delay: float = DELAY_SECONDS, timeout: int = 20,
              allow_local: bool = False) -> tuple[list[Path], str]:
    """Fetch each URL once. Returns (saved files, '' or the block that ended the run)."""
    if len(urls) > MAX_URLS:
        raise Refused(f"at most {MAX_URLS} URLs per run; this is a test, not a crawl")
    for url in urls:
        reason = refuse_reason(url, allow_local)
        if reason:
            raise Refused(f"{url}: {reason}")
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for n, url in enumerate(urls):
        host = urllib.parse.urlsplit(url).hostname or ""
        if _blocks(out_dir).get(host) == date.today().isoformat():
            return saved, f"{host} blocked an earlier request today; not trying again"
        if n:
            time.sleep(delay)
        try:
            status, final, body = _get(url, timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = str(getattr(exc, "reason", exc))
            hint = (f"\n    The environment's network policy does not allow {host}. Add it under Allowed "
                    "domains in the cloud environment's settings (docs/CAPTURING-PAGES.md)."
                    if "Tunnel connection failed" in reason else "")
            print(f"  {url}: {type(exc).__name__}: {reason}{hint}", file=sys.stderr)
            continue
        except Refused as exc:
            print(f"  {url}: {exc}", file=sys.stderr)
            continue
        why = block_reason(status, final, body)
        if why:
            _record_block(out_dir, host)
            return saved, f"{host}: {why}"
        if status >= 400:
            print(f"  {url}: HTTP {status}", file=sys.stderr)
            continue
        path = out_dir / _name(url)
        path.write_text(body, encoding="utf-8")
        saved.append(path)
    return saved, ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jobscan.fetchpage", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--out-dir", default=".", help="where the pages are saved (default: here)")
    args = ap.parse_args(argv)
    try:
        saved, blocked = fetch_all(args.urls, Path(args.out_dir))
    except Refused as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for path in saved:
        try:
            job = clip.parse(path.read_text(encoding="utf-8"), "test")[0]
            verdict = f"JobPosting found: {job.title} — {job.company}"
        except clip.ClipError as exc:
            verdict = f"clip: {exc}"
        print(f"saved {path} ({path.stat().st_size:,} bytes)\n  {verdict}")
    if blocked:
        print(f"BLOCKED: {blocked}. Stopped, and not retrying today. Nothing was done to get past it. "
              "Save the page in your own browser instead (docs/CAPTURING-PAGES.md).", file=sys.stderr)
        return 3
    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())
