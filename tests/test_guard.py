import json
import subprocess
import sys
from pathlib import Path

GUARD = Path(__file__).resolve().parents[1] / "scripts/hooks/guard.py"


def run(call):
    return subprocess.run([sys.executable, str(GUARD)], input=json.dumps(call),
                          capture_output=True, text=True)


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def test_blocks_submission_and_answer_approval():
    for cmd in ("python -m jobscan.apply run --data ../career-data",
                "python -m jobscan.apply questions approve 3",
                "python -m jobscan.apply questions set 3 x"):
        r = run(bash(cmd))
        assert r.returncode == 2 and "BLOCKED" in r.stderr, cmd


def test_blocks_force_push_main_push_and_hook_skipping():
    for cmd in ("git push --force origin feat", "git push origin main", "git push origin HEAD:main",
                "git push -u origin feat --no-verify", "sed -i s/x/allow_auto_submit/ f"):
        assert run(bash(cmd)).returncode == 2, cmd


def test_blocks_edits_to_owner_files():
    for p in ("/d/career-data/authorization.yaml", "/d/config.yaml", "/d/profiles/rui/profile.yaml"):
        assert run({"tool_name": "Edit", "tool_input": {"file_path": p}}).returncode == 2, p


def test_allows_the_routine_and_normal_development():
    for cmd in ("python -m jobscan.pipeline prepare --data ../career-data",
                "python -m jobscan.apply summary --data ../career-data",
                "python -m jobscan.apply enqueue --data ../career-data",
                "git push -u origin claude/laughing-fermat-kr1wik",
                "git push origin main-fix-branch", "python -m pytest -q"):
        assert run(bash(cmd)).returncode == 0, cmd
    assert run({"tool_name": "Edit", "tool_input": {"file_path": "/d/src/jobscan/pipeline.py"}}).returncode == 0
    assert run({"tool_name": "Read", "tool_input": {}}).returncode == 0


def test_bad_input_does_not_block():
    r = subprocess.run([sys.executable, str(GUARD)], input="not json", capture_output=True, text=True)
    assert r.returncode == 0
