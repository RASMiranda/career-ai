"""Human-readable status of the application queue (markdown + email fragment)."""

import html
from datetime import datetime, timedelta, timezone

from ..normalize import is_http_url
from . import tracker
from .faillog import EXPLAIN
from .queue import Queue


def _recent(item: dict, days: int) -> bool:
    ts = item.get("updated") or item.get("created")
    return bool(ts) and datetime.fromisoformat(ts) >= datetime.now(timezone.utc) - timedelta(days=days)


def sections(queue: Queue, days: int = 7, profile: str | None = None,
             follow_up_days: int = tracker.DEFAULT_FOLLOW_UP_DAYS) -> dict[str, list[dict]]:
    """``profile`` limits the sections to one profile's items (None = all)."""
    pick = lambda *s: sorted((i for i in queue.by_status(*s)  # noqa: E731
                              if profile is None or i.get("profile") == profile),
                             key=lambda i: -i.get("fit", 0))
    return {
        "failed": pick("failed"),
        "queued": pick("queued"),
        "filled": pick("filled"),
        "submitted": [i for i in pick("submitted") if _recent(i, days)],
        "in_progress": pick("replied", "interview", "offer"),
        "follow_up": tracker.follow_ups_due(queue, days=follow_up_days, profile=profile),
    }


def _funnel_line(queue: Queue, profile: str | None = None) -> str:
    counts = tracker.funnel(queue, profile)
    if not counts:
        return ""
    applied = sum(counts[s] for s in tracker.FUNNEL)
    parts = [f"{applied} applied"] + [f"{counts[s]} {s}" for s in
                                      ("replied", "interview", "offer", "rejected") if counts[s]]
    rate = tracker.response_rate(counts)
    return " · ".join(parts) + (f" · {rate}% answered" if rate is not None else "")


def _line(i: dict) -> str:
    cv = f" · CV {i['cv']}" if i.get("cv") else ""
    return f"{i['title']} — {i['company']} · fit {i.get('fit', '?')}{cv} · `{i['candidate_key'][:8]}`"


def render_markdown(queue: Queue, days: int = 7, follow_up_days: int = tracker.DEFAULT_FOLLOW_UP_DAYS) -> str:
    s = sections(queue, days, follow_up_days=follow_up_days)
    out = ["# Applications", ""]
    funnel = _funnel_line(queue)
    if funnel:
        out += [f"**Tracker:** {funnel}", ""]
    if s["in_progress"]:
        out += ["## In progress — they answered", ""]
        for i in s["in_progress"]:
            note = (i.get("notes") or [{}])[-1].get("text")
            out += [f"- {_line(i)} · **{i['status']}**" + (f" — {note}" if note else "")]
        out.append("")
    if s["follow_up"]:
        out += ["## Follow up — no answer yet", ""]
        for i in s["follow_up"]:
            kit = f" · draft: `{i['kit']}/follow-up-email.md`" if i.get("kit") else ""
            out += [f"- {_line(i)} · applied {tracker._applied_on(i) or '?'}{kit}",
                    f"  - Sent it: `python -m jobscan.apply followed-up {i['candidate_key'][:8]}`"
                    f" · got an answer: `track {i['candidate_key'][:8]} --status replied`"]
        out.append("")
    if s["failed"]:
        out += ["## Apply manually — automatic submission did not work", ""]
        for i in s["failed"]:
            code = i.get("error_code", "INTERNAL")
            out += [f"- {_line(i)}", f"  - Why: {EXPLAIN.get(code, code)}",
                    f"  - Link: {i['url']}"]
        out.append("")
    if s["queued"]:
        out += ["## Waiting for your decision", ""]
        for i in s["queued"]:
            out += [f"- {_line(i)}", f"  - Link: {i['url']}",
                    f"  - Not auto-approved: {'; '.join(i.get('policy_notes', [])) or '—'}",
                    f"  - Approve: `python -m jobscan.apply approve {i['candidate_key'][:8]}`"
                    f" · Applied yourself: `done` · Not interested: `skip`",
                    f"  - Documents: {i['kit']}" if i.get("kit") else
                    f"  - Draft letter and prep: `python -m jobscan.kit prepare {i['candidate_key'][:8]}`"]
        out.append("")
    if s["filled"]:
        out += ["## Form filled — you still need to click submit", ""]
        out += [f"- {_line(i)} · {i['url']}" for i in s["filled"]] + [""]
    if s["submitted"]:
        out += [f"## Submitted automatically (last {days} days)", ""]
        out += [f"- {_line(i)}" for i in s["submitted"]] + [""]
    if len(out) == 2:
        out.append("_Nothing pending._")
    return "\n".join(out)


def render_html(queue: Queue, days: int = 7, profile: str | None = None,
                follow_up_days: int = tracker.DEFAULT_FOLLOW_UP_DAYS) -> str:
    e = html.escape
    s = sections(queue, days, profile, follow_up_days)
    # In-progress items are context, not a reason to send an email on their own.
    if not any(v for k, v in s.items() if k != "in_progress"):
        return ""

    def row(i, extra=""):
        url = i["url"] if is_http_url(i.get("url", "")) else ""
        link = f' · <a href="{e(url)}" style="color:#0b5cad">Open posting</a>' if url else ""
        return (f'<li style="margin:0 0 8px"><b>{e(i["title"])}</b> — {e(i["company"])} '
                f'· fit {e(str(i.get("fit", "?")))}'
                + (f' · CV {e(i["cv"])}' if i.get("cv") else "")
                + f' · <code>{e(i["candidate_key"][:8])}</code>'
                f'{link}{extra}</li>')

    parts = ['<div style="font-family:system-ui,Arial,sans-serif;max-width:640px;margin-top:24px">',
             '<h3 style="margin:0 0 8px">Applications</h3>']
    funnel = _funnel_line(queue, profile)
    if funnel:
        parts.append(f'<p style="color:#666;margin:0 0 8px">{e(funnel)}</p>')
    if s["in_progress"]:
        parts.append('<p><b>In progress</b> — they answered</p><ul>')
        parts += [row(i, f' · <b>{e(i["status"])}</b>') for i in s["in_progress"]] + ["</ul>"]
    if s["follow_up"]:
        parts.append('<p><b>Follow up</b> — no answer yet</p><ul>')
        parts += [row(i, f' · applied {e(str(tracker._applied_on(i) or "?"))}') for i in s["follow_up"]] + ["</ul>"]
    if s["failed"]:
        parts.append('<p><b>Apply manually</b> — automatic submission did not work</p><ul>')
        parts += [row(i, f'<br><span style="color:#8a6d3b">{e(EXPLAIN.get(i.get("error_code", ""), "Unexpected error."))}</span>')
                  for i in s["failed"]] + ["</ul>"]
    if s["queued"]:
        parts.append('<p><b>Waiting for your decision</b></p><ul>')
        parts += [row(i, f'<br><span style="color:#666">{e("; ".join(i.get("policy_notes", [])))}</span>')
                  for i in s["queued"]] + ["</ul>"]
    if s["filled"]:
        parts.append('<p><b>Form filled — click submit yourself</b></p><ul>')
        parts += [row(i) for i in s["filled"]] + ["</ul>"]
    if s["submitted"]:
        parts.append(f'<p><b>Submitted automatically</b> (last {days} days)</p><ul>')
        parts += [row(i) for i in s["submitted"]] + ["</ul>"]
    parts.append("</div>")
    return "\n".join(parts)
