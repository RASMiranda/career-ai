"""Run the scan in as few model turns as possible.

    python -m jobscan.pipeline prepare --data D   collect + deterministic triage; prints the
                                                  brief the model must score. When nothing
                                                  needs scoring it finishes the whole run.
    python -m jobscan.pipeline finish  --data D   merge decisions, validate, enqueue, report;
                                                  commits and pushes when there is no email.
    python -m jobscan.pipeline commit  --data D   after the emails were sent: persist + push.
    python -m jobscan.pipeline show KEY --data D  full description of one candidate.

Every step is the same code as before (collect, validate, apply enqueue, report);
this only chains them so the model does not spend a turn on each one.
"""

import argparse
import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

from . import collect, report, triage, validate
from .apply import cli as apply_cli
from .apply.queue import Queue
from .apply.summary import count_failures
from .config import ConfigError, data_root, load_authorization, load_config

PUBLISH_PATHS = ("reports", "state", "applications", "logs")


def _read(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def publish(root: Path, message: str) -> str:
    """Commit reports/state/applications/logs and push to main, else to claude/job-scan.

    Returns where the state went. Also pushes the current claude/* session branch
    (best effort): the cloud harness warns about unpushed commits on it, which
    would cost the model another turn.
    """
    _git(root, "add", *[p for p in PUBLISH_PATHS if (root / p).exists()])
    if _git(root, "diff", "--cached", "--quiet").returncode == 0:
        return "nothing to commit"
    done = _git(root, "commit", "-qm", message)
    if done.returncode:
        raise RuntimeError(f"git commit failed: {done.stderr.strip()[:200]}")
    target = "main"
    if _git(root, "push", "origin", "HEAD:main").returncode:
        if _git(root, "push", "origin", "HEAD:claude/job-scan").returncode:
            raise RuntimeError("push rejected for main and claude/job-scan")
        target = "claude/job-scan (main was rejected)"
    branch = _git(root, "branch", "--show-current").stdout.strip()
    if branch.startswith("claude/") and branch != "claude/job-scan":
        _git(root, "push", "origin", f"HEAD:refs/heads/{branch}")
    return target


def _paths(work: Path) -> dict[str, Path]:
    return {"candidates": work / "candidates.json", "auto": work / "auto-decisions.json",
            "brief": work / "brief.md", "model": work / "decisions.json",
            "all": work / "all-decisions.json", "out": work / "out"}


def _setup(args):
    try:
        root = data_root(args.data)
        cfg = load_config(root)
        auth = load_authorization(root)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return None
    if not auth.get("active"):
        print("authorization.yaml: active is not true. STOP: nothing was run.", file=sys.stderr)
        return None
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    return root, cfg, work


def _quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def cmd_prepare(args) -> int:
    ctx = _setup(args)
    if not ctx:
        return 2
    root, cfg, work = ctx
    p = _paths(work)
    for stale in (p["model"], p["all"], p["auto"], p["brief"]):
        stale.unlink(missing_ok=True)

    rc = collect.main(["--data", str(root), "--out", str(p["candidates"])])
    if rc:
        return rc
    payload = _read(p["candidates"], {})
    try:
        auto, to_score, deferred = triage.triage(payload, cfg)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    held = {c["candidate_key"] for c in deferred}
    payload["candidates"] = [c for c in payload["candidates"] if c["candidate_key"] not in held]
    payload["triage"] = {"auto_discarded": len(auto), "to_score": len(to_score), "deferred": len(deferred)}
    _write(p["candidates"], payload)
    _write(p["auto"], auto)

    print(f"\ntriage: {len(auto)} auto-discarded by prefilter, {len(to_score)} need scoring"
          + (f", {len(deferred)} deferred to the next run (cap)" if deferred else ""))
    if not to_score:
        print("NOTHING TO SCORE: finishing the run automatically. If a SEND list follows (e.g. waiting "
              "applications), the email is still due: send it, then run commit.\n")
        return _finish(root, cfg, work, commit_if_no_email=True)

    brief = triage.render_brief(to_score, cfg, root)
    p["brief"].write_text(brief, encoding="utf-8")
    print("\nBRIEF: score ONLY these candidates. Read each profile's criteria file and CV cards "
          "first. Write a JSON array to " + str(p["model"]) + " with one decision per key below "
          "(keep why/caution under 25 words), then run: python -m jobscan.pipeline finish --data "
          f"{args.data}\n")
    print(brief)
    return 0


def _finish(root: Path, cfg: dict, work: Path, commit_if_no_email: bool) -> int:
    p = _paths(work)
    payload = _read(p["candidates"], None)
    if payload is None:
        print("no candidates.json: run `pipeline prepare` first", file=sys.stderr)
        return 2
    model = _read(p["model"], [])
    model = model.get("decisions", []) if isinstance(model, dict) else model
    decided = {d.get("candidate_key") for d in model if isinstance(d, dict)}
    merged = [d for d in _read(p["auto"], []) if d["candidate_key"] not in decided] + list(model)
    _write(p["all"], merged)

    data = ["--data", str(root)]
    rc = validate.main([*data, "--candidates", str(p["candidates"]), "--decisions", str(p["all"])])
    if rc:
        print("STOP: validation failed. Nothing was enqueued, sent or saved.", file=sys.stderr)
        return rc
    for cmd in (["enqueue", "--candidates", str(p["candidates"]), "--decisions", str(p["all"])],
                ["summary"]):
        rc = _quiet(apply_cli.main, [*data, *cmd])
        if rc:
            print(f"STOP: apply {cmd[0]} failed ({rc}).", file=sys.stderr)
            return rc
    rc = report.main([*data, "--candidates", str(p["candidates"]), "--decisions", str(p["all"]),
                      "--out-dir", str(p["out"])])
    if rc:
        return rc

    deliveries = _read(p["out"] / "deliveries.json", [])
    sendable = [d for d in deliveries if d["send"]]
    queue = Queue(root)
    counts = payload.get("counts", {})
    dispo = [d["disposition"] for d in merged]
    print("\nRUN SUMMARY")
    print(f"  collected new: {counts.get('new', '?')} · already seen: {counts.get('already_seen', '?')}"
          f" · blacklisted: {counts.get('blacklisted', '?')} · source errors: {len(payload.get('errors', []))}")
    print(f"  auto-discarded: {payload.get('triage', {}).get('auto_discarded', 0)}"
          f" · deferred: {payload.get('triage', {}).get('deferred', 0)}"
          f" · scored by the model: {len(model)}")
    print(f"  email: {dispo.count('email')} · low-confidence: {dispo.count('low-confidence')}"
          f" · discarded: {dispo.count('discarded')}")
    print(f"  applications waiting: {len(queue.by_status('queued'))} · auto-approved: "
          f"{len(queue.by_status('approved'))} · to apply by hand: {count_failures(queue)} "
          f"(failed or approved but never submitted)")

    if sendable:
        print("\nSEND these emails with the Gmail connector, to the listed addresses and no others, "
              "then run: python -m jobscan.pipeline commit --data " + str(root))
        for d in sendable:
            print(f"  to {', '.join(d['to'])} | subject: {d['subject']} | body file: {d['body']}")
        return 0
    print("\nNo email to send.")
    if commit_if_no_email:
        return _commit(root, work)
    return 0


def _commit(root: Path, work: Path) -> int:
    p = _paths(work)
    rc = report.main(["--data", str(root), "--candidates", str(p["candidates"]),
                      "--decisions", str(p["all"]), "--out-dir", str(p["out"]), "--commit"])
    if rc:
        return rc
    counts = _read(p["candidates"], {}).get("counts", {})
    try:
        where = publish(root, f"job-scan {_read(p['candidates'], {}).get('generated_on', '')}: "
                              f"{counts.get('new', 0)} new")
    except RuntimeError as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 1
    print(f"state saved: {where}")
    return 0


def cmd_finish(args) -> int:
    ctx = _setup(args)
    return 2 if not ctx else _finish(*ctx, commit_if_no_email=True)


def cmd_commit(args) -> int:
    ctx = _setup(args)
    return 2 if not ctx else _commit(ctx[0], ctx[2])


def cmd_show(args) -> int:
    ctx = _setup(args)
    if not ctx:
        return 2
    payload = _read(_paths(ctx[2])["candidates"], {"candidates": []})
    hits = [c for c in payload["candidates"] if c["candidate_key"].startswith(args.key)]
    if len(hits) != 1:
        print(f"{args.key!r} matches {len(hits)} candidates", file=sys.stderr)
        return 1
    c = hits[0]
    print(f"{c['title']} | {c['company']} | {c.get('location', '')} | {c.get('contract_type', '')}\n")
    print(triage.clean(c.get("description"))[:args.chars])
    return 0


def main(argv=None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data")
    common.add_argument("--work", default="/tmp", help="where candidates/decisions/emails are written")
    ap = argparse.ArgumentParser(prog="jobscan.pipeline", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prepare", "finish", "commit"):
        sub.add_parser(name, parents=[common])
    show = sub.add_parser("show", parents=[common])
    show.add_argument("key")
    show.add_argument("--chars", type=int, default=4000)
    args = ap.parse_args(argv)
    return {"prepare": cmd_prepare, "finish": cmd_finish, "commit": cmd_commit,
            "show": cmd_show}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
