"""PreToolUse approval gate (AI-native SDLC playbook: gates are hooks, ADR-024).

Reads the tool call as JSON on stdin; exit 2 blocks it and the stderr line tells the agent why.
Deterministic and fast: no network, no model. Mirrors the "never" rules in CLAUDE.md.
"""
import json
import re
import sys
from pathlib import PurePath

PROTECTED_FILES = {"authorization.yaml", "config.yaml", "profile.yaml"}
BASH_RULES = [
    (r"jobscan\.apply\s+run\b", "submitting applications is the owner's machine only (CLAUDE.md)"),
    (r"jobscan\.apply\s+questions\s+(approve|reject|set)\b", "approving form answers is the owner's decision"),
    (r"git\s+push\b[^|;&]*(--force\b|\s-f\b|\+\S*main\b)", "never force-push"),
    (r"git\s+push\b[^|;&]*\b(origin\s+)?(HEAD:)?(refs/heads/)?main\b(?!-)", "main is reached only by pull request"),
    (r"--no-verify\b", "do not skip hooks"),
    (r"allow_auto_submit", "never flip allow_auto_submit"),
]


def check(call: dict) -> str | None:
    tool, args = call.get("tool_name", ""), call.get("tool_input") or {}
    if tool in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        path = args.get("file_path") or args.get("notebook_path") or ""
        if PurePath(path).name in PROTECTED_FILES:
            return f"{PurePath(path).name} is owner-only (authorization, config and profiles)"
    if tool == "Bash":
        cmd = args.get("command", "")
        for pattern, why in BASH_RULES:
            if re.search(pattern, cmd):
                return why
    return None


def main() -> int:
    try:
        call = json.load(sys.stdin)
    except ValueError:
        return 0
    reason = check(call)
    if reason:
        print(f"BLOCKED by scripts/hooks/guard.py: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
