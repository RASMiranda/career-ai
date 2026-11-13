"""ADR-057: a stage whose own output is already on the branch does not run. Helper, CLI, workflow order, and the post
step run under a fake `gh` (no network, no real GitHub)."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from jobscan import sdlc

ROOT = Path(__file__).resolve().parents[1]
WF = yaml.safe_load((ROOT / ".github" / "workflows" / "sdlc.yml").read_text())
STEPS = WF["jobs"]["stage"]["steps"]
for _s in STEPS:
    _s.setdefault("name", _s.get("uses", ""))
SKIP = next(s for s in STEPS if s["name"].startswith("Skip a stage whose output"))
POST = next(s for s in STEPS if s["name"].startswith("Post the report"))
N = 7
WORK = f"docs/intents/{N}-add-a-thing"


def decision(stage):
    return sdlc.decide({"action": "labeled", "sender": {"type": "User", "login": "o"}, "label": {"name": f"agent:{stage}"},
                        "issue": {"number": N, "title": "Add a thing", "state": "open", "locked": False,
                                  "author_association": "OWNER", "labels": []}}, [f"agent/{N}-add-a-thing"])


@pytest.mark.parametrize("stage,file", [("intent", "intent.md"), ("spec", "spec.md"), ("plan", "plan.md")])
def test_the_stage_file_present_means_skipped_and_absent_means_normal(tmp_path, stage, file):
    d = decision(stage)
    assert d["stage"] == stage and d["writes"] == [f"{WORK}/{file}"]
    assert sdlc.done_file(d, str(tmp_path)) is None                   # absent: the stage runs
    (tmp_path / WORK).mkdir(parents=True)
    (tmp_path / WORK / file).write_text("x")
    assert sdlc.done_file(d, str(tmp_path)) == f"{WORK}/{file}"        # present: skipped


@pytest.mark.parametrize("stage", ["build", "review", "release", "support-l1", "support-l2", "support-l3"])
def test_other_stages_are_never_skipped_even_if_a_file_exists(tmp_path, stage):
    d = decision(stage) if stage != "build" else {**decision("plan"), "stage": "build",
                                                  "writes": ["src/**", "tests/**", "docs/**", "README.md"]}
    (tmp_path / WORK).mkdir(parents=True)
    for name in ("intent.md", "spec.md", "plan.md"):
        (tmp_path / WORK / name).write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x")
    assert sdlc.done_file(d, str(tmp_path)) is None


def test_the_skip_line_is_exactly_the_wording_the_owner_asked_for():
    assert sdlc.skip_line("spec", f"{WORK}/spec.md") == (
        f"Stage `spec` skipped: `{WORK}/spec.md` is already on the branch. "
        "To redo it, delete that file on the branch and apply the label again.")


def test_the_cli_writes_one_line_and_the_output_flag(tmp_path, monkeypatch):
    dec = tmp_path / "decision.json"
    dec.write_text(json.dumps(decision("spec")))
    (tmp_path / WORK).mkdir(parents=True)
    (tmp_path / WORK / "spec.md").write_text("x")
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.chdir(tmp_path)
    comment = tmp_path / "comment.md"
    assert sdlc.main(["skipped", "--decision", str(dec), "--comment", str(comment)]) == 0
    assert comment.read_text().splitlines() == [sdlc.skip_line("spec", f"{WORK}/spec.md")]
    assert out.read_text() == "skip=true\n"
    (tmp_path / WORK / "spec.md").unlink()
    comment.unlink()
    out.unlink()
    assert sdlc.main(["skipped", "--decision", str(dec), "--comment", str(comment)]) == 0
    assert not comment.exists() and out.read_text() == "skip=false\n"


def test_the_skip_step_runs_after_the_branch_is_checked_out_and_before_anything_else_that_costs_or_calls_out():
    names = [s["name"] for s in STEPS]
    i = names.index(SKIP["name"])
    assert names.index("Check out the issue's branch") < i < names.index("Fetch the issue and PR comments (gh)")
    assert names.index("Run the stage agents") > i
    assert SKIP["if"] == "${{ steps.d.outputs.run == 'true' && env.stop != 'true' }}" or \
        "env.stop != 'true'" in SKIP["if"]
    assert "GH_TOKEN" not in (SKIP.get("env") or {})                     # trusted code, no token, no network
    assert "skipped=true" in SKIP["run"] and "stop=true" in SKIP["run"]


def test_the_skip_step_adds_no_stage_label_and_the_post_step_returns_before_it():
    run = POST["run"]
    head = run.split("exit 0")[0]
    assert '"$SKIPPED" = "true"' in head and "--remove-label" in head and "--add-label" not in head
    assert run.index('"$SKIPPED" = "true"') < run.index("--add-label \"stage:$STAGE\"")


def test_the_checkout_of_the_branch_respects_a_stop():
    co = next(s for s in STEPS if s["name"] == "Check out the issue's branch")
    assert "env.stop != 'true'" in co["if"]


def _post_run(tmp_path, env_extra):
    """Run the real post step's shell with a fake gh that logs its arguments; return (log lines, post body)."""
    if not shutil.which("bash"):
        pytest.skip("needs bash")
    (tmp_path / ".sdlc").mkdir(exist_ok=True)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    log = tmp_path / "gh.log"
    gh = bin_ / "gh"
    gh.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\nexit 0\n')
    gh.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "PYTHONPATH": str(ROOT / "src"),
           "TRUSTED_SRC": str(ROOT / "src"), "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "NUMBER": str(N), "TRIGGER_LABEL": "agent:spec",
           "STAGE": "spec", "ROLES": "product-owner", "REJECTED": "success", "BRANCH": "", "AGENT_REPORT": "true",
           "SKIPPED": "", "STOP": "", **env_extra}
    subprocess.run(["bash", "-e", "-c", POST["run"]], cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    calls = log.read_text().splitlines() if log.exists() else []
    body = (tmp_path / ".sdlc" / "post.md")
    return calls, body.read_text() if body.exists() else None


def test_a_skipped_run_posts_one_line_and_removes_only_the_trigger_label(tmp_path):
    (tmp_path / ".sdlc").mkdir()
    (tmp_path / ".sdlc" / "comment.md").write_text(sdlc.skip_line("spec", f"{WORK}/spec.md") + "\n")
    calls, _ = _post_run(tmp_path, {"SKIPPED": "true", "STOP": "true"})
    assert calls == [f"issue comment {N} --body-file .sdlc/comment.md",
                     f"issue edit {N} --remove-label agent:spec"]
    assert not any("add-label" in c for c in calls)


def test_a_stopped_run_posts_its_message_without_a_next_gate(tmp_path):
    (tmp_path / ".sdlc").mkdir()
    (tmp_path / ".sdlc" / "comment.md").write_text("Stage `spec` needs `docs/x/intent.md` on the branch.\n")
    calls, body = _post_run(tmp_path, {"STOP": "true"})
    assert body is not None and "Next gate" not in body and "needs" in body
    assert f"issue edit {N} --add-label stage:spec --remove-label agent:spec" in calls


def test_a_normal_run_still_names_the_next_gate(tmp_path):
    (tmp_path / ".sdlc").mkdir()
    (tmp_path / ".sdlc" / "comment.md").write_text("The spec is written.\n")
    _, body = _post_run(tmp_path, {})
    assert "**Next gate (yours):** Resolve every flagged concern, then apply `agent:plan`." in body


def test_the_missing_report_wording_says_what_a_human_does():
    run = POST["run"]
    assert "Open this run's log" in run and "ADR-055" in run
    assert "The stage ended without a report from the agent." in run
