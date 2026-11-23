"""The review round cap, the round marker, the diff-only scope and the verifier's switch (ADR-068).

The review is posted inside the stage comment on the issue. Each posted review carries a hidden marker,
``<!-- sdlc-review round=N sha=<sha> -->``, written by trusted code in the post step. A round is counted only from a
comment whose author is the workflow's own bot, so a marker typed by anyone else on a public issue is ignored.

Pure, except ``is_ancestor`` (one ``git merge-base`` call). Nothing here reads an agent's file: the comments come from
a trusted step that ran after the build agent, and the cap and the verifier switch come from repository variables.
"""
import re
import subprocess

from . import review

BOT_LOGIN = "github-actions[bot]"
DEFAULT_MAX_ROUNDS = 3                 # used when SDLC_MAX_REVIEW_ROUNDS is unset or not a whole number
DIFF_ONLY_FROM = 3                     # from this round, the review reads only the change since the last reviewed commit
MARKER_RE = re.compile(r"<!-- sdlc-review round=(\d{1,6}) sha=([0-9a-f]{40}) -->")
SHA_RE = re.compile(r"[0-9a-f]{40}")
MAX_EARLIER = 60
UNREADABLE = "unreadable"


def parse_max(value) -> int:
    """A whole number of rounds, or DEFAULT_MAX_ROUNDS. 0 is a whole number and blocks every review."""
    text = "" if value is None else str(value).strip()
    if text.isascii() and text.isdigit():
        return int(text)
    return DEFAULT_MAX_ROUNDS


def verify_enabled(value) -> bool:
    """The verifier is on only for the exact string ``true``: "True", "1" and " true" leave it off."""
    return value == "true"


def marker_text(round_no: int, sha: str) -> str:
    return f"<!-- sdlc-review round={round_no} sha={sha} -->"


def count_rounds(comments) -> dict | None:
    """{count, base, earlier} from the bot's own comments, or None when the comments are not a list (unreadable).

    ``count`` is the markers found; ``base`` is the sha of the latest one; ``earlier`` is the finding lines of the
    reviews those markers belong to, most recent last (untrusted text: the caller frames it)."""
    if not isinstance(comments, list):
        return None
    count, base, earlier = 0, "", []
    for comment in comments:
        if not isinstance(comment, dict) or not isinstance(comment.get("user"), dict):
            continue
        if comment["user"].get("login") != BOT_LOGIN:
            continue                    # a marker from anyone else is text, never a round
        body = comment.get("body") if isinstance(comment.get("body"), str) else ""
        found = MARKER_RE.findall(body)
        if not found:
            continue
        count += len(found)
        base = found[-1][1]
        review_part = body.split("**Review**", 1)[1] if "**Review**" in body else ""
        earlier += [line.strip()[:review.MAX_LINE] for line in review_part.splitlines()
                    if review.FINDING_RE.fullmatch(line.strip())]
    return {"count": count, "base": base, "earlier": earlier[-MAX_EARLIER:]}


def _comment(mention: str, text: str) -> str:
    return f"{mention} {text}" if mention else text


def plan(state, head: str, max_value, verify_value, mention: str = "") -> dict:
    """What this push's review may do. ``state`` is count_rounds() or None; ``head`` is the pushed commit.

    Round r = markers counted + 1. A review runs when r <= cap, so a cap of 0 blocks every review. An unreadable state or
    commit blocks too (fail closed). When blocked, ``comment`` is the one short comment the post step writes."""
    cap = parse_max(max_value)
    if state is None or not SHA_RE.fullmatch(head or ""):
        text = ("no review ran: the issue's comments or the pushed commit could not be read, so the review round cap "
                "could not be checked. Re-apply `agent:build` once the run can read them.")
        return {"round": 0, "cap": cap, "blocked": True, "reason": UNREADABLE, "review": False, "verify": False,
                "base": "", "earlier": [], "marker": "", "comment": _comment(mention, text) + "\n"}
    r = state["count"] + 1
    if r > cap:
        text = (f"the review round cap was reached: this would be review round {r} and the cap is {cap} (repository "
                "variable SDLC_MAX_REVIEW_ROUNDS). No review ran on this commit. Step back and reconsider the approach "
                "before another round; the build report above is unchanged.")
        return {"round": r, "cap": cap, "blocked": True, "reason": "cap", "review": False, "verify": False, "base": "",
                "earlier": [], "marker": "", "comment": _comment(mention, text) + "\n"}
    base = state["base"] if r >= DIFF_ONLY_FROM and SHA_RE.fullmatch(state["base"] or "") else ""
    return {"round": r, "cap": cap, "blocked": False, "reason": "", "review": True,
            "verify": verify_enabled(verify_value), "base": base, "earlier": list(state["earlier"]),
            "marker": marker_text(r, head), "comment": ""}


def is_ancestor(base: str, rev: str = "HEAD") -> bool:
    """True when ``base`` (a full sha, checked first so it cannot read as an option) is an ancestor of ``rev``."""
    if not SHA_RE.fullmatch(base or ""):
        return False
    done = subprocess.run(["git", "merge-base", "--is-ancestor", base, rev], capture_output=True, text=True)
    return done.returncode == 0
