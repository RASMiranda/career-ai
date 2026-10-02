"""python -m jobscan.apply <command>

  enqueue     put today's emailable matches into the queue (applies policy)
  approve K…  you approve queued items (K = first 6+ chars of the key)
  skip K…     not interested            done K…   you applied by hand
  run         process approved items (see modes below)
  summary     markdown/html status for the daily email
  bundle      redacted failure bundle to paste into Claude Code
  blacklist   list | test "Company name"

Modes (config.yaml -> apply.mode):
  off       nothing is queued
  manual    queue only; you apply yourself                      (default)
  assisted  opens a visible browser, fills the form, YOU click submit
  auto      submits unattended, within caps, only if authorization.yaml allows
"""

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

import yaml

from .. import cv
from ..blacklist import Blacklist
from ..config import ConfigError, data_root, load_authorization, load_config
from . import faillog, policy, summary
from .adapters import ApplyFailure, Code, detect_ats, pick_adapter
from .queue import Queue


def _applicant(root: Path) -> tuple[dict, dict]:
    path = root / "applicant.yaml"
    if not path.is_file():
        raise ConfigError(f"Missing {path} (copy applicant.example.yaml and fill it in)")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    app, answers = data.get("applicant") or {}, data.get("answers") or {}
    missing = [k for k in ("first_name", "last_name", "email") if not app.get(k)]
    if missing:
        raise ConfigError(f"applicant.yaml is missing: {', '.join(missing)}")
    return app, answers


def _cv_for(item: dict, root: Path, cfg: dict) -> str | None:
    """The CV the AI chose for this job, else the profile's default."""
    profile = cv.profile_by_id(cfg, item.get("profile"))
    if profile is None:
        return None
    variant = item.get("cv") or cv.settings(profile)["default"]
    if not variant:
        return None
    path = cv.find(cv.local_files(root, profile), variant)
    if path is None or not path.is_file():
        raise ApplyFailure(Code.CV_MISSING, f"CV variant {variant!r} not found", "prepare")
    return str(path)


def cmd_enqueue(args, root, cfg, auth):
    acfg = policy.apply_cfg(cfg)
    if acfg["mode"] == "off":
        print("apply.mode is off — nothing queued")
        return 0
    cands = {c["candidate_key"]: c for c in
             json.loads(Path(args.candidates).read_text(encoding="utf-8"))["candidates"]}
    decisions = json.loads(Path(args.decisions).read_text(encoding="utf-8"))
    decisions = decisions.get("decisions", []) if isinstance(decisions, dict) else decisions
    q, added = Queue(root), {"approved": 0, "queued": 0, "skipped": 0}

    for d in decisions:
        key = d["candidate_key"]
        if d["disposition"] != "email" or q.has(key) or key not in cands:
            continue
        c = cands[key]
        item = {"title": c["title"], "company": c["company"], "url": c["url"],
                "source": c["source"], "fit": d["fit"], "tier": d["tier"],
                "confidence": d["confidence"], "profile": c.get("profile"),
                "cv": d.get("cv") or ""}
        bl = Blacklist.from_config(cfg, c.get("profile"))
        status, notes = policy.initial_status(item, acfg, auth, q, bl)
        q.add(key, {**item, "status": status, "policy_notes": notes,
                    "approval": "policy" if status == "approved" else None})
        added[status] += 1
    q.save()
    print(f"enqueued: {added}")
    return 0


def _mark(args, root, status):
    q = Queue(root)
    for prefix in args.keys:
        key = q.resolve(prefix)
        extra = {"approval": "user"} if status == "approved" else {}
        q.set(key, status, **extra)
        print(f"{status}: {q.items[key]['title']} — {q.items[key]['company']}")
    q.save()
    return 0


def cmd_run(args, root, cfg, auth):
    acfg = policy.apply_cfg(cfg)
    mode = args.mode or acfg["mode"]
    if mode in ("off", "manual"):
        print(f"mode is {mode!r}: nothing to run. Use --mode assisted, or set apply.mode.")
        return 0
    if mode == "auto" and not args.dry_run and not policy.auto_switch_on(auth):
        print("auto mode needs authorization.yaml → application_submission."
              "allow_auto_submit: true AND acknowledged_on: <date>. Refusing.", file=sys.stderr)
        return 2

    applicant, answers = _applicant(root)
    secrets = [applicant.get(k, "") for k in ("first_name", "last_name", "email", "phone")]
    flog, q = faillog.FailureLog(root, secrets), Queue(root)
    submit = mode == "auto" and not args.dry_run
    headless = (mode == "auto" or args.dry_run) and not args.headed
    quota = policy.remaining_quota(acfg, q) if submit else 10**6
    limit = min(quota, args.limit or 10**6)
    if submit and quota == 0:
        print("daily/weekly submission cap reached — nothing to do")
        return 0

    run_id = uuid.uuid4().hex[:8]
    todo = sorted(q.by_status("approved"), key=lambda i: -i.get("fit", 0))[:limit]
    print(f"run {run_id}: mode={mode} dry_run={args.dry_run} items={len(todo)}")

    for n, item in enumerate(todo):
        key, t0 = item["candidate_key"], time.time()
        label = f"{item['title']} — {item['company']}"
        try:
            if Blacklist.from_config(cfg, item.get("profile")).match(item):
                raise ApplyFailure(Code.BLOCKED_BY_POLICY, "company is blacklisted", "gate")
            adapter = pick_adapter(item["url"], acfg["auto"]["allowed_adapters"])
            if adapter is None:
                raise ApplyFailure(Code.NO_ADAPTER, "no adapter for host", "gate")
            result = adapter.apply(item, applicant, answers, _cv_for(item, root, cfg),
                                   submit=submit, headless=headless, hold=mode == "assisted")
            if result.status == "submitted":
                q.set(key, "submitted"); print(f"  submitted  {label}")
            elif args.dry_run:
                print(f"  dry-run ok {label} (fields: {len(result.filled)})")
            else:
                q.set(key, "filled"); print(f"  filled     {label}")
            item["attempts"].append({"run": run_id, "outcome": result.status})
        except ApplyFailure as fail:
            _record_failure(flog, q, item, fail, mode, run_id, t0, args.dry_run)
            print(f"  FAILED     {label} → {fail.code}")
        except Exception as exc:  # never let one job abort the batch
            fail = ApplyFailure(Code.INTERNAL, type(exc).__name__, "run")
            _record_failure(flog, q, item, fail, mode, run_id, t0, args.dry_run)
            print(f"  FAILED     {label} → INTERNAL ({type(exc).__name__})")
        q.save()
        if submit and n < len(todo) - 1:
            time.sleep(acfg["delay_seconds"])
    return 0


def _record_failure(flog, q, item, fail, mode, run_id, t0, dry_run):
    flog.write({
        "run_id": run_id, "candidate_key": item["candidate_key"],
        "company": item["company"], "title": item["title"], "url": item["url"],
        "ats": detect_ats(item["url"]), "adapter": detect_ats(item["url"]),
        "mode": "dry-run" if dry_run else mode, "step": fail.step,
        "error_code": fail.code, "message": fail.message, "details": fail.details,
        "duration_ms": int((time.time() - t0) * 1000),
    })
    item["attempts"].append({"run": run_id, "outcome": "failed", "error_code": fail.code})
    if not dry_run:
        q.set(item["candidate_key"], "failed", error_code=fail.code, error_message=fail.message)


def cmd_summary(args, root, cfg, auth):
    q = Queue(root)
    md = summary.render_markdown(q, args.days)
    if args.html:
        Path(args.html).write_text(summary.render_html(q, args.days), encoding="utf-8")
    (root / "reports").mkdir(exist_ok=True)
    (root / "reports" / "applications.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


def cmd_bundle(args, root, cfg, auth):
    entries = faillog.FailureLog(root).read_since(args.days)
    if not entries:
        print("no failures in that window")
        return 0
    text = faillog.bundle(entries)
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"wrote {args.out} ({len(entries)} failures) — paste it into Claude Code in career-ai")
    return 0


def cmd_blacklist(args, root, cfg, auth):
    bl = Blacklist.from_config(cfg)
    if args.action == "list":
        for e in bl.entries:
            print(f"- {e['name']}  aliases={sorted(e['squashed'])}  domains={e['domains']}")
        return 0
    hit = bl.match({"company": args.name, "url": args.url or ""})
    print(f"BLOCKED by {hit}" if hit else "not blacklisted")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jobscan.apply", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("enqueue")
    p.add_argument("--candidates", default="candidates.json")
    p.add_argument("--decisions", default="decisions.json")
    for name in ("approve", "skip", "done"):
        sub.add_parser(name).add_argument("keys", nargs="+")
    p = sub.add_parser("run")
    p.add_argument("--mode", choices=["assisted", "auto"])
    p.add_argument("--dry-run", action="store_true", help="fill forms, never submit")
    p.add_argument("--headed", action="store_true", help="show the browser")
    p.add_argument("--limit", type=int)
    p = sub.add_parser("summary")
    p.add_argument("--html")
    p.add_argument("--days", type=int, default=7)
    p = sub.add_parser("bundle")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--out", default="failures.md")
    p = sub.add_parser("blacklist")
    p.add_argument("action", choices=["list", "test"])
    p.add_argument("name", nargs="?", default="")
    p.add_argument("--url")
    args = ap.parse_args(argv)

    try:
        root = data_root(args.data)
        cfg, auth = load_config(root), load_authorization(root)
        if args.cmd in ("approve", "skip", "done"):
            return _mark(args, root, {"approve": "approved", "skip": "skipped", "done": "done"}[args.cmd])
        return {"enqueue": cmd_enqueue, "run": cmd_run, "summary": cmd_summary,
                "bundle": cmd_bundle, "blacklist": cmd_blacklist}[args.cmd](args, root, cfg, auth)
    except (ConfigError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
