"""Step 4: render the report and the email body, then update state.

All external text is HTML-escaped and every link is checked to be http(s)
before it reaches the template: job descriptions are untrusted input.
"""

import argparse
import html
import json
import sys
from datetime import date
from pathlib import Path

from .apply.queue import Queue
from .apply.policy import apply_cfg
from .decide import repo_slug
from .apply.summary import count_failures, render_failures
from .apply.summary import render_html as render_applications
from . import feedback
from .config import ConfigError, data_root, load_authorization, load_config, recipients
from .normalize import is_http_url
from .state import Journal, Seen

PENDING_FIT_FLOOR = 70
PENDING_LIMIT = 6


def _bucket(candidates: dict, decisions: list, profiles: list | None = None) -> tuple[list, list]:
    """Split decisions into matches and "to verify" items.

    Each candidate's profile may set ``pending_fit_floor`` and ``pending_limit``
    (profile.yaml); the module defaults apply when it does not.
    """
    cand = {c["candidate_key"]: c for c in candidates["candidates"]}
    settings = {p["id"]: p for p in profiles or []}
    matches, pending = [], {}
    for d in decisions:
        c = cand.get(d["candidate_key"])
        if not c:
            continue
        row = {**c, **d}
        prof = settings.get(c.get("profile"), {})
        if d["disposition"] == "email":
            matches.append(row)
        elif (d["disposition"] == "low-confidence"
              and d["fit"] >= prof.get("pending_fit_floor", PENDING_FIT_FLOOR)
              and is_http_url(c.get("url", ""))):
            pending.setdefault(c.get("profile"), []).append(row)
    matches.sort(key=lambda r: r["fit"], reverse=True)
    shown = []
    for pid, rows in pending.items():
        rows.sort(key=lambda r: r["fit"], reverse=True)
        shown += rows[:settings.get(pid, {}).get("pending_limit", PENDING_LIMIT)]
    shown.sort(key=lambda r: r["fit"], reverse=True)
    return matches, shown


def render_markdown(day: str, matches: list, pending: list, errors: list) -> str:
    lines = [f"# Job scan — {day}", "",
             f"{len(matches)} match(es), {len(pending)} to verify.", ""]
    if not matches:
        lines += ["_No confirmed matches today._", ""]
    for m in matches:
        lines += [
            f"## {m['title']} — {m['company']}",
            f"- **Fit** {m['fit']} ({m['confidence']} confidence) · {m['tier']}",
            f"- **Where** {m.get('location') or 'n/a'} · {m.get('contract_type') or 'n/a'}"
            + (f" · {m['salary']}" if m.get("salary") else ""),
            f"- **Why** {m['why']}",
            f"- **Caution** {m.get('caution') or '—'}",
            f"- **Next** {m.get('next_action') or '—'}"
            + (f" · **CV** {m['cv']}" if m.get("cv") else ""),
            f"- **Link** {m['url']} ({m['source']})", "",
        ]
    if pending:
        lines += ["## To verify (thin source data)", ""]
        lines += [f"- {p['title']} — {p['company']} · fit {p['fit']} · {p['url']}"
                  for p in pending] + [""]
    if errors:
        lines += ["## Run notes", ""] + [f"- {e}" for e in errors] + [""]
    lines += ["---", "_Nothing was submitted or sent on your behalf._"]
    return "\n".join(lines)


def _card(row: dict) -> str:
    e = html.escape
    url = row["url"] if is_http_url(row.get("url", "")) else ""
    link = f'<a href="{e(url)}" style="color:#0b5cad">Open posting</a>' if url else "no link"
    meta = " · ".join(filter(None, [e(row.get("location") or ""),
                                    e(row.get("contract_type") or ""),
                                    e(row.get("salary") or ""),
                                    e(f"CV: {row['cv']}") if row.get("cv") else ""]))
    return (
        '<div style="border:1px solid #ddd;border-radius:8px;padding:12px;margin:0 0 12px">'
        f'<div style="font-weight:600;font-size:15px">{e(row["title"])}</div>'
        f'<div style="color:#555">{e(row["company"])}{" · " + meta if meta else ""}</div>'
        f'<div style="margin:8px 0"><b>Fit {row["fit"]}</b> '
        f'({e(row["confidence"])}) · {e(row.get("tier",""))}</div>'
        f'<div>{e(row["why"])}</div>'
        + (f'<div style="color:#8a6d3b;margin-top:6px">⚠ {e(row["caution"])}</div>'
           if row.get("caution") else "")
        + f'<div style="margin-top:8px">{link}</div></div>'
    )


def render_email(day: str, matches: list, pending: list, extra_html: str = "", urgent_html: str = "",
                 repo: str = feedback.DEFAULT_REPO) -> str:
    """``urgent_html`` (applications to do by hand) goes first: it is the part that needs you today."""
    body = [f'<div style="font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:640px">',
            f'<h2 style="margin:0 0 4px">Job scan · {html.escape(day)}</h2>',
            f'<p style="color:#666;margin:0 0 16px">{len(matches)} match(es), '
            f'{len(pending)} to verify.</p>']
    if urgent_html:
        body.append(urgent_html)
    body += [_card(m) for m in matches] or ['<p>No confirmed matches today.</p>']
    if pending:
        body.append('<h3>To verify</h3>')
        body += [_card(p) for p in pending]
    body.append(extra_html)
    body.append(feedback.links_html(day, repo))
    body.append('<p style="color:#888;font-size:12px;margin-top:20px">'
                'Automated scan. Applications are only ever submitted if you enabled it; see the Applications section.</p></div>')
    return "\n".join(body)


def build_deliveries(day: str, cfg: dict, candidates: dict, decisions: list,
                     queue: Queue | None = None, out_dir: Path = Path("."),
                     decision_repo: str | None = None) -> list[dict]:
    """One email per profile, addressed only to that profile's notify.email.

    Writes ``email-<profile>.html`` and returns the delivery manifest. ``send`` is
    False when the profile has nothing to report, so no email goes out.
    """
    deliveries = []
    for profile in cfg["profiles"]:
        pid = profile["id"]
        own = {"candidates": [c for c in candidates["candidates"] if c.get("profile") == pid]}
        matches, pending = _bucket(own, decisions, [profile])
        wait = int(profile.get("follow_up_days") or apply_cfg(cfg)["follow_up_days"])
        apps = render_applications(queue, profile=pid, follow_up_days=wait, failures=False,
                                   decision_repo=decision_repo) if queue else ""
        repo = (cfg.get("feedback") or {}).get("repo") or feedback.DEFAULT_REPO
        urgent = render_failures(queue, pid, repo=repo, decision_repo=decision_repo) if queue else ""
        by_hand = count_failures(queue, pid) if queue else 0
        body = out_dir / f"email-{pid}.html"
        body.write_text(render_email(day, matches, pending, apps, urgent, repo), encoding="utf-8")
        deliveries.append({
            "profile": pid,
            "to": recipients(profile),
            "subject": f"[Job Scan] {day} — {len(matches)} matches"
                       + (f" — ⚠ {by_hand} to apply by hand" if by_hand else ""),
            "body": str(body),
            "matches": len(matches),
            "pending": len(pending),
            "apply_by_hand": by_hand,
            # A failed application always produces an email, even on a day with no new matches.
            "send": bool(matches or pending or apps or urgent),
        })
    return deliveries


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Render report and email; update state.")
    ap.add_argument("--data")
    ap.add_argument("--candidates", default="candidates.json")
    ap.add_argument("--decisions", default="decisions.json")
    ap.add_argument("--out-dir", default=".",
                    help="where email-<profile>.html and deliveries.json are written")
    ap.add_argument("--commit", action="store_true",
                    help="persist seen-state and journal (omit for a dry run)")
    args = ap.parse_args(argv)

    try:
        root = data_root(args.data)
        cfg = load_config(root)
        load_authorization(root)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    candidates = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    decisions = json.loads(Path(args.decisions).read_text(encoding="utf-8"))
    if isinstance(decisions, dict):
        decisions = decisions.get("decisions", [])

    journal = Journal(root)
    if journal.has_open_send():
        print("a previous delivery is stuck in 'sending' — review it by hand first",
              file=sys.stderr)
        return 1

    day = candidates.get("generated_on") or date.today().isoformat()
    matches, pending = _bucket(candidates, decisions, cfg["profiles"])

    md = render_markdown(day, matches, pending, candidates.get("errors", []))
    (root / "reports").mkdir(exist_ok=True)
    (root / "reports" / f"{day}.md").write_text(md, encoding="utf-8")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    deliveries = build_deliveries(day, cfg, candidates, decisions, Queue(root), out_dir, repo_slug(root))
    (out_dir / "deliveries.json").write_text(json.dumps(deliveries, indent=2), encoding="utf-8")

    print(f"report: reports/{day}.md")
    print(f"deliveries: {out_dir / 'deliveries.json'}")
    for d in deliveries:
        status = f"send to {', '.join(d['to']) or 'NOBODY'}" if d["send"] else "nothing to send"
        print(f"  {d['profile']}: {d['matches']} match(es), {d['pending']} to verify"
              f" · {d['body']} · {status}")
    print(f"matches: {len(matches)}  to verify: {len(pending)}")

    if not args.commit:
        print("dry run — state not written (pass --commit after the email is sent)")
        return 0

    seen = Seen(root)
    for row in [*matches, *pending]:
        seen.add(row["candidate_key"], row["title"], row["company"])
    for c in candidates["candidates"]:
        seen.add(c["candidate_key"], c["title"], c["company"])
    seen.save()
    journal.record(day, "completed", matches=len(matches), pending=len(pending))
    journal.save()
    print("state committed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
