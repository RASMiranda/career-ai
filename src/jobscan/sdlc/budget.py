"""Usage budget gate for the sdlc workflow (ADR-032).

The agents run on the owner's Pro subscription, so the limit that matters is Pro usage, not dollars. This module
turns the workflow's own run history into "agent minutes used" over two rolling windows and decides whether one
more run may start. The decision is pure: it takes the runs from the GitHub API, the current run id, `now` and
two caps, and does no I/O. Only `main` (the workflow's entry point) calls `gh`.

Minutes are an approximation. A run's duration is `updated_at - run_started_at`, which also counts time spent on
gate-only steps, queueing inside the job and the last bookkeeping write; it is not the model's own time. A run
counts only if its whole duration is at least `MIN_RUN_SECONDS` (gate-only runs last seconds) and it was not
cancelled. The current run is excluded. A run that has not finished counts up to `now`. Each counted run adds the
part of it that falls inside the window, so usage slides off as the run ages out.

Fail closed: a missing or non-numeric cap uses the default, never "unlimited"; a cap of 0 blocks everything.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

MIN_RUN_SECONDS = 30
DEFAULT_CAP_24H = 60
DEFAULT_CAP_7D = 240
PER_PAGE = 100
MAX_PAGES = 30
DAY = timedelta(hours=24)
WEEK = timedelta(days=7)


def parse_time(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def parse_cap(value, default):
    """A whole number of minutes >= 0, else `default`. Never None, never unlimited."""
    try:
        text = str(value).strip()
        if not text.isascii() or not text.isdigit():
            return default
        return int(text)
    except (TypeError, ValueError):
        return default


def _intervals(runs, current_run_id, now):
    out = []
    for r in runs:
        if str(r.get("id")) == str(current_run_id) or r.get("conclusion") == "cancelled":
            continue
        start = parse_time(r.get("run_started_at"))
        if start is None:
            continue
        end = parse_time(r.get("updated_at")) if r.get("status") == "completed" else now
        if end is None or end - start < timedelta(seconds=MIN_RUN_SECONDS):
            continue
        out.append((start, end))
    return out


def _used_seconds(intervals, at, window):
    lo = at - window
    return sum(max(0.0, (min(e, at) - max(s, lo)).total_seconds()) for s, e in intervals)


def _retry_after(intervals, now, cap_24h, cap_7d):
    """First minute at which both windows are within their caps, or None if no cap can ever be met (cap 0)."""
    if cap_24h == 0 or cap_7d == 0:
        return None
    for k in range(1, int(WEEK.total_seconds() // 60) + 2):
        t = now + timedelta(minutes=k)
        if (_used_seconds(intervals, t, DAY) <= cap_24h * 60 and _used_seconds(intervals, t, WEEK) <= cap_7d * 60):
            return t
    return None


def evaluate(runs, current_run_id, now, cap_24h, cap_7d):
    """Minutes used in the last 24 hours and 7 days, and whether another run is allowed.

    Exactly at a cap is allowed; anything over is blocked; a cap of 0 blocks everything.
    """
    iv = _intervals(runs, current_run_id, now)
    s24, s7 = _used_seconds(iv, now, DAY), _used_seconds(iv, now, WEEK)
    allowed = (cap_24h > 0 and cap_7d > 0 and s24 <= cap_24h * 60 and s7 <= cap_7d * 60)
    return {"used_24h": round(s24 / 60, 1), "used_7d": round(s7 / 60, 1), "cap_24h": cap_24h, "cap_7d": cap_7d,
            "allowed": allowed, "retry_after": None if allowed else _retry_after(iv, now, cap_24h, cap_7d)}


def collect_runs(fetch_page, now):
    """Pages of runs, newest first, until one reaches back past 7 days (or is short or empty).

    `fetch_page(page, per_page, created_since)` returns a list of run dicts. `created_since` is a date a day
    earlier than the window, so a run that started just inside it is not missed.
    """
    since = (now - WEEK - DAY).date().isoformat()
    runs = []
    for page in range(1, MAX_PAGES + 1):
        batch = fetch_page(page, PER_PAGE, since) or []
        runs.extend(batch)
        if len(batch) < PER_PAGE:
            break
        oldest = min((parse_time(r.get("run_started_at") or r.get("created_at")) or now for r in batch))
        if oldest < now - WEEK:
            break
    return runs


def render_summary(stage, result):
    r = result
    if r["allowed"]:
        decision = "allowed"
    else:
        decision = "blocked (nothing ran)"
    return (f"### Budget gate\n\n- Stage: `{stage}`\n"
            f"- Agent minutes used, last 24h: {r['used_24h']} of {r['cap_24h']}\n"
            f"- Agent minutes used, last 7d: {r['used_7d']} of {r['cap_7d']}\n"
            f"- Decision: {decision}\n")


def render_comment(result):
    r = result
    when = (r["retry_after"].strftime("%Y-%m-%d %H:%M UTC") if r["retry_after"]
            else "the cap is raised (SDLC_MAX_AGENT_MIN_24H / SDLC_MAX_AGENT_MIN_7D)")
    return (f"@RASMiranda: Budget gate: used {r['used_24h']} of {r['cap_24h']} agent-minutes in the last 24h "
            f"({r['used_7d']} of {r['cap_7d']} in 7d). Nothing ran. Try again after {when}.")


def _gh_page(page, per_page, created_since):
    out = subprocess.run(
        ["gh", "api", "-X", "GET", f"repos/{os.environ['GITHUB_REPOSITORY']}/actions/workflows/sdlc.yml/runs",
         "-f", f"per_page={per_page}", "-f", f"page={page}", "-f", f"created=>={created_since}"],
        check=True, capture_output=True, text=True).stdout
    return json.loads(out).get("workflow_runs", [])


def main(argv=None):
    """Exit 0 allowed, 3 blocked. Any other exit (history unreadable) is treated as blocked by the workflow."""
    ap = argparse.ArgumentParser(prog="jobscan.sdlc.budget")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--stage", default="")
    ap.add_argument("--max-24h", default="")
    ap.add_argument("--max-7d", default="")
    ap.add_argument("--summary", help="file to append the summary to (GITHUB_STEP_SUMMARY)")
    ap.add_argument("--comment", help="file to write the issue comment to when blocked")
    a = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    result = evaluate(collect_runs(_gh_page, now), a.run_id, now, parse_cap(a.max_24h, DEFAULT_CAP_24H),
                      parse_cap(a.max_7d, DEFAULT_CAP_7D))
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as f:
            f.write(render_summary(a.stage, result))
    if not result["allowed"]:
        if a.comment:
            with open(a.comment, "w", encoding="utf-8") as f:
                f.write(render_comment(result) + "\n")
        print(f"::warning title=Budget gate::{render_comment(result)}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
