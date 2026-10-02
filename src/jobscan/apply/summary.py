"""Human-readable status of the application queue (markdown + email fragment)."""

import html
from datetime import datetime, timedelta, timezone

from ..normalize import is_http_url
from .faillog import EXPLAIN
from .queue import Queue


def _recent(item: dict, days: int) -> bool:
    ts = item.get("updated") or item.get("created")
    return bool(ts) and datetime.fromisoformat(ts) >= datetime.now(timezone.utc) - timedelta(days=days)


def sections(queue: Queue, days: int = 7) -> dict[str, list[dict]]:
    pick = lambda *s: sorted(queue.by_status(*s), key=lambda i: -i.get("fit", 0))  # noqa: E731
    return {
        "failed": pick("failed"),
        "queued": pick("queued"),
        "filled": pick("filled"),
        "submitted": [i for i in pick("submitted") if _recent(i, days)],
    }


def _line(i: dict) -> str:
    return f"{i['title']} — {i['company']} · fit {i.get('fit', '?')} · `{i['candidate_key'][:8]}`"


def render_markdown(queue: Queue, days: int = 7) -> str:
    s = sections(queue, days)
    out = ["# Applications", ""]
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
                    f" · Applied yourself: `done` · Not interested: `skip`"]
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


def render_html(queue: Queue, days: int = 7) -> str:
    e = html.escape
    s = sections(queue, days)
    if not any(s.values()):
        return ""

    def row(i, extra=""):
        url = i["url"] if is_http_url(i.get("url", "")) else ""
        link = f' · <a href="{e(url)}" style="color:#0b5cad">Open posting</a>' if url else ""
        return (f'<li style="margin:0 0 8px"><b>{e(i["title"])}</b> — {e(i["company"])} '
                f'· fit {e(str(i.get("fit", "?")))} · <code>{e(i["candidate_key"][:8])}</code>'
                f'{link}{extra}</li>')

    parts = ['<div style="font-family:system-ui,Arial,sans-serif;max-width:640px;margin-top:24px">',
             '<h3 style="margin:0 0 8px">Applications</h3>']
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
