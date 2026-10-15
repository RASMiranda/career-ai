"""One-click "I applied" / "not interested" from the email (ADR-025).

The email carries a link that opens a pre-filled GitHub issue in the private data repo. The owner
presses *Submit new issue* (GitHub's own login is the authentication), a workflow in that repo runs
``python -m jobscan.decide`` with the issue title, and the job leaves the queue. No server, no
hosting. Only ``done`` and ``skip`` are reachable this way: approving a submission stays a command
the owner types (CLAUDE.md).
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, urlencode

from .apply.queue import Queue

ACTIONS = {"done": "done", "skip": "skipped"}
LABEL = "job-decision"
TITLE_RE = re.compile(r"^(done|skip) ([0-9a-f]{8})$")
REMOTE_RE = re.compile(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?/?$")


def repo_slug(root: Path) -> str | None:
    """``owner/repo`` of the data repo, from its git remote; None when it is not a GitHub checkout."""
    try:
        url = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    m = REMOTE_RE.search(url)
    return m.group(1) if m else None


def link(slug: str | None, action: str, key: str) -> str:
    """The pre-filled new-issue URL for ``action`` on the job whose key starts with ``key[:8]``."""
    if not slug or action not in ACTIONS:
        return ""
    q = urlencode({"title": f"{action} {key[:8]}", "labels": LABEL,
                   "body": "Press *Submit new issue*. A workflow records it and closes this issue."},
                  quote_via=quote)
    return f"https://github.com/{slug}/issues/new?{q}"


def parse_title(title: str) -> tuple[str, str]:
    m = TITLE_RE.match(title.strip())
    if not m:
        raise ValueError("title must be exactly 'done <8 hex>' or 'skip <8 hex>'")
    return m.group(1), m.group(2)


def apply_decision(root: Path, title: str) -> str:
    action, prefix = parse_title(title)
    q = Queue(root)
    key = q.resolve(prefix)
    item = q.items[key]
    if item.get("status") in ("submitted", "replied", "interview", "offer", "rejected", "withdrawn"):
        raise ValueError(f"already {item['status']}: nothing to change")
    q.set(key, ACTIONS[action])
    q.save()
    return f"{ACTIONS[action]}: {item['title']} — {item['company']}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Apply an email-link decision (run by the data repo's workflow).")
    ap.add_argument("--data", required=True)
    ap.add_argument("--title", required=True, help="the issue title, 'done KEY8' or 'skip KEY8'")
    args = ap.parse_args(argv)
    try:
        print(apply_decision(Path(args.data), args.title))
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
