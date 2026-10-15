"""Report a problem, suggest a feature, ask for help: a link that opens a pre-filled GitHub issue form.

    python -m jobscan.feedback [bug|feature|support] [--title T] [--open]

The scan email carries the same three links, and each failed application a "Report this failure" link.
Clicking one opens the issue form (``.github/ISSUE_TEMPLATE/``) in your browser, logged in as you, so the issue
is created by you and, when you own the repository, starts the agentic SDLC (docs/SDLC.md, ADR-025).

Nothing personal is ever put in a link: only the version, the day, and for a failure the error code, the host
and the mode. Never a company, a job title, a URL path, a name or an address. The repository is public.
"""

import argparse
import html
import re
import sys
import urllib.parse
import webbrowser
from urllib.parse import urlsplit

from . import __version__

DEFAULT_REPO = "RASMiranda/career-ai"
KINDS = {"bug": ("bug.yml", "[bug] ", "Report a problem"),
         "feature": ("feature.yml", "[feature] ", "Suggest a feature"),
         "support": ("support.yml", "[help] ", "Ask for help")}
MAX_URL = 1800
_REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/(?!\.{1,2}$)[A-Za-z0-9_.-]{1,100}$")   # GitHub owner/name rules
_CODE = re.compile(r"^[A-Z_]{3,40}$")


def issue_url(kind: str, repo: str = DEFAULT_REPO, title: str = "", **fields: str) -> str:
    """The new-issue URL for a form, pre-filled with ``title`` and the form fields given by id."""
    template, prefix, _ = KINDS[kind]
    if not _REPO.match(repo):
        raise ValueError(f"not a GitHub repository name: {repo!r}")
    params = {"template": template}
    if title.strip():
        params["title"] = prefix + " ".join(title.split())[:120]
    for key, value in fields.items():
        if value:
            params[key] = " ".join(str(value).split())[:400] if key == "context" else str(value)[:900]
    url = f"https://github.com/{repo}/issues/new?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return url if len(url) <= MAX_URL else f"https://github.com/{repo}/issues/new?template={template}"


def context(day: str = "") -> str:
    return f"career-ai {__version__}" + (f" · scan {day}" if day else "")


def failure_url(item: dict, repo: str = DEFAULT_REPO) -> str:
    """A bug form for one failed application, filled with the error code, the host and the mode only."""
    code = item.get("error_code") or "INTERNAL"
    code = code if _CODE.match(code) else "INTERNAL"
    host = (urlsplit(item.get("url", "")).hostname or "unknown host")[:80]
    what = (f"An application did not go through.\n\nError code: {code}\nSite: {host}\n"
            f"Status: {item.get('status', 'failed')}")
    return issue_url("bug", repo, f"apply failed: {code} on {host}", what_happened=what,
                     context=context(), redacted_output="")


def links_html(day: str = "", repo: str = DEFAULT_REPO) -> str:
    """The three links for the foot of the scan email."""
    anchors = [f'<a href="{html.escape(issue_url(kind, repo, context=context(day)))}" '
               f'style="color:#0b5cad;text-decoration:none;border:1px solid #0b5cad;border-radius:4px;'
               f'padding:4px 8px;margin-right:6px;display:inline-block">{label}</a>'
               for kind, (_, _, label) in KINDS.items()]
    return ('<p style="margin:16px 0 0;font-size:13px">' + "".join(anchors) +
            '<br><span style="color:#888">Opens a GitHub form with nothing personal in it. Do not paste names, '
            'emails or CV text: the repository is public.</span></p>')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jobscan.feedback", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", nargs="?", default="bug", choices=sorted(KINDS))
    ap.add_argument("--title", default="")
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--open", action="store_true", help="open it in your browser")
    args = ap.parse_args(argv)
    try:
        url = issue_url(args.kind, args.repo, args.title, context=context())
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(url)
    if args.open and not webbrowser.open(url):
        print("could not open a browser; copy the link above", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
