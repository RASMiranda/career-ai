"""ADR-036: jobscan steps that run after an agent use the code from the trigger commit, not the agent's branch.
Parses the workflow file; no network, no git."""
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "sdlc.yml"
SECRETS = ("GH_TOKEN", "GITHUB_TOKEN", "ANTHROPIC", "CLAUDE_CODE_OAUTH_TOKEN")
STAGE_AGENTS = "Run the stage agents"
REVIEW_AGENTS = "Run the review agents"
LOAD = "Trusted jobscan code"


def steps():
    sts = yaml.safe_load(WORKFLOW.read_text())["jobs"]["stage"]["steps"]
    for s in sts:
        s.setdefault("name", s.get("uses", ""))
    return sts


def names():
    return [s["name"] for s in steps()]


def idx(prefix):
    return [i for i, n in enumerate(names()) if n.startswith(prefix)]


def after(agent_name):
    return steps()[names().index(agent_name) + 1:]


def test_every_jobscan_call_after_the_stage_agents_uses_the_trusted_copy_without_the_cwd():
    calls = [s for s in after(STAGE_AGENTS) if "jobscan" in s.get("run", "") and "python" in s["run"]]
    assert calls
    for s in calls:
        assert 'PYTHONPATH="$TRUSTED_SRC"' in s["run"] and "python -P" in s["run"], s["name"]
        assert "PYTHONPATH=src" not in s["run"], s["name"]
    for s in after(STAGE_AGENTS):
        assert "PYTHONPATH=src" not in s.get("run", ""), s["name"]


BRANCH_CHECKOUT = "Check out the issue's branch"
SKIP_STEP = "Skip a stage whose output is already on the branch (ADR-057)"
FRAME_STEP = "Frame the issue as untrusted input and write the stage prompt"


def test_the_decide_and_budget_steps_keep_src_because_they_run_before_the_branch_is_checked_out():
    # Before the branch checkout the checkout is the trigger commit (ADR-036), so src is trusted there.
    before = steps()[:names().index(BRANCH_CHECKOUT)]
    assert any("PYTHONPATH=src" in s.get("run", "") for s in before)


def test_no_helper_between_the_branch_checkout_and_the_agent_imports_the_branch_src():
    # ADR-036 (i.F9): after `git checkout` the working tree is the issue's branch, which an agent wrote. A `run:` step
    # there must import from the trusted copy, never from `src` in the working tree.
    n = names()
    window = steps()[n.index(BRANCH_CHECKOUT) + 1:n.index(STAGE_AGENTS)]
    assert window, "the checkout and the agent step are not in the expected order"
    for s in window:
        assert "PYTHONPATH=src" not in s.get("run", ""), s["name"]
        assert "PYTHONPATH=src" not in str(s.get("env", "")), s["name"]
    assert any(s["name"] in (SKIP_STEP, FRAME_STEP) for s in window)     # the helpers are still there, just trusted


def test_the_pre_agent_trusted_load_sits_right_after_the_branch_checkout_and_before_the_skip_step():
    n = names()
    clear = idx("Trusted jobscan code, before the agent (1 of 3)")
    fetch = idx("Trusted jobscan code, before the agent (2 of 3)")
    use = idx("Trusted jobscan code, before the agent (3 of 3)")
    assert len(clear) == len(fetch) == len(use) == 1
    c, f, u = clear[0], fetch[0], use[0]
    assert n.index(BRANCH_CHECKOUT) < c < f < u < n.index(SKIP_STEP)
    assert n[c - 1] == BRANCH_CHECKOUT and n[u + 1] == "Check the stage's input exists (the gate before it)"
    assert n.index(SKIP_STEP) < n.index(FRAME_STEP) < n.index(STAGE_AGENTS)
    assert "rm -rf trusted" in steps()[c]["run"] and ".git/info/exclude" in steps()[c]["run"]
    assert "TRUSTED_SRC" in steps()[u]["run"] and "test -f trusted/src/jobscan/sdlc/__init__.py" in steps()[u]["run"]


def test_the_pre_agent_checkout_has_the_same_parameters_as_the_post_agent_one():
    pre = next(s for s in steps() if s["name"].startswith("Trusted jobscan code, before the agent (2 of 3)"))
    post = next(s for s in steps() if s["name"].startswith("Trusted jobscan code (2 of 3)"))
    assert pre["uses"] == post["uses"] == "actions/checkout@v7"
    assert pre["with"] == post["with"] == {"ref": "${{ github.sha }}", "path": "trusted", "sparse-checkout": "src",
                                           "persist-credentials": False}
    assert pre["if"] == post["if"] == "always() && steps.d.outputs.run == 'true'"


def test_the_helpers_before_the_agent_use_the_trusted_src_with_python_dash_p():
    # The helpers import only src/ (stdlib otherwise); -P keeps the working directory off sys.path, so a file the agent
    # planted in the workspace cannot shadow the package.
    for s in steps()[names().index(BRANCH_CHECKOUT) + 1:names().index(STAGE_AGENTS)]:
        for line in s.get("run", "").splitlines():
            if "-m jobscan.sdlc" in line:
                assert 'PYTHONPATH="$TRUSTED_SRC" python -P -m jobscan.sdlc' in line, (s["name"], line)


def test_the_trusted_code_is_a_second_checkout_pinned_to_the_trigger_commit_and_never_git_archive():
    text = WORKFLOW.read_text()
    assert "git archive" not in text
    checkouts = [s for s in steps() if s["name"].startswith(LOAD) and "uses" in s]
    assert len(checkouts) == 3              # ADR-036 (i.F9): one before the agent, one after each of the two agent runs
    for s in checkouts:
        assert s["uses"] == "actions/checkout@v7"   # bumped to Node 24 (ADR-057 item i.F5e)
        assert s["with"] == {"ref": "${{ github.sha }}", "path": "trusted", "sparse-checkout": "src",
                             "persist-credentials": False}
        assert "always()" in s["if"] and not s.get("env")


def test_each_trusted_load_follows_its_agent_run_and_precedes_the_steps_that_import_jobscan():
    n = names()
    clear = idx("Trusted jobscan code (1 of 3)"), idx("Trusted jobscan code, again after the reviewers (1 of 3)")
    use = idx("Trusted jobscan code (3 of 3)"), idx("Trusted jobscan code, again after the reviewers (3 of 3)")
    assert len(clear[0]) == len(clear[1]) == len(use[0]) == len(use[1]) == 1
    c1, c2, u1, u2 = clear[0][0], clear[1][0], use[0][0], use[1][0]
    assert n.index(STAGE_AGENTS) < c1 < u1 < n.index("Check what the agent changed")
    assert u1 < idx("Commit and push")[0] < n.index(REVIEW_AGENTS)
    # the second load comes after both agent runs, before the reviewer check and the post step
    assert n.index(REVIEW_AGENTS) < c2 < u2 < n.index("Reject any change the reviewers made") < idx("Post the report")[0]
    # a clear step runs right before its checkout, and the folder is hidden from git status
    assert n[c1 + 1].startswith("Trusted jobscan code (2 of 3)") and n[c2 + 1].startswith("Trusted jobscan code, again")
    for i in (c1, c2):
        assert "rm -rf trusted" in steps()[i]["run"] and ".git/info/exclude" in steps()[i]["run"]


def test_the_load_steps_have_no_token():
    for s in steps():
        if s["name"].startswith(LOAD):
            assert not [k for k in (s.get("env") or {}) if any(x in k for x in SECRETS)], s["name"]
            assert "GH_TOKEN" not in str(s) and "secrets." not in str(s) and "github.token" not in str(s)


def test_the_use_step_exports_the_src_of_the_trusted_checkout():
    for s in steps():
        if s["name"].startswith(LOAD) and "(3 of 3)" in s["name"]:
            assert 'echo "TRUSTED_SRC=$GITHUB_WORKSPACE/trusted/src" >> "$GITHUB_ENV"' in s["run"]
            assert "test -f trusted/src/jobscan/sdlc/__init__.py" in s["run"]


def test_every_token_step_after_the_stage_agents_that_imports_jobscan_runs_after_a_trusted_load():
    start = names().index(STAGE_AGENTS)
    for i, s in enumerate(steps()):
        if i > start and "GH_TOKEN" in (s.get("env") or {}) and "jobscan" in s.get("run", ""):
            assert any(n.startswith(LOAD) for n in names()[:i]), s["name"]
            assert 'PYTHONPATH="$TRUSTED_SRC"' in s["run"], s["name"]


# ------------------------------------------------ the pre-agent helpers, run through their real shell (i.F9)
def _shell(step_run, cwd, extra):
    import os
    import shutil
    import subprocess

    import pytest
    if not shutil.which("bash"):
        pytest.skip("needs bash")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}     # the step must not depend on a PYTHONPATH=src
    env.update({"TRUSTED_SRC": str(ROOT / "src"), "GITHUB_ENV": str(cwd / "github.env"),
                "GITHUB_OUTPUT": str(cwd / "github.out"), "NUMBER": "7", **extra})
    return subprocess.run(["bash", "-e", "-c", step_run], cwd=cwd, env=env, capture_output=True, text=True)


def _decision_and_branch(cwd, stage_file=None):
    from jobscan import sdlc
    event = {"action": "labeled", "sender": {"type": "User", "login": "o"}, "label": {"name": "agent:spec"},
             "issue": {"number": 7, "title": "Add a thing", "body": "", "state": "open", "locked": False,
                       "author_association": "OWNER", "labels": []}}
    (cwd / ".sdlc").mkdir(exist_ok=True)
    (cwd / ".sdlc" / "decision.json").write_text(json.dumps(sdlc.decide(event, ["agent/7-add-a-thing"])))
    if stage_file:
        (cwd / "docs/intents/7-add-a-thing").mkdir(parents=True, exist_ok=True)
        (cwd / "docs/intents/7-add-a-thing" / stage_file).write_text("x")
    return event


def test_the_skip_step_runs_for_real_from_the_trusted_src_and_stops_only_when_the_file_is_on_the_branch(tmp_path):
    from jobscan import sdlc
    skip = next(s for s in steps() if s["name"] == SKIP_STEP)
    _decision_and_branch(tmp_path, stage_file="spec.md")
    run = _shell(skip["run"], tmp_path, {})
    assert run.returncode == 0, run.stderr
    assert (tmp_path / ".sdlc" / "comment.md").read_text().splitlines() == [
        sdlc.skip_line("spec", "docs/intents/7-add-a-thing/spec.md")]
    assert "stop=true" in (tmp_path / "github.env").read_text() and "skipped=true" in (tmp_path / "github.env").read_text()
    (tmp_path / "docs/intents/7-add-a-thing/spec.md").unlink()
    (tmp_path / "github.env").unlink()
    run = _shell(skip["run"], tmp_path, {})
    assert run.returncode == 0, run.stderr
    assert not (tmp_path / ".sdlc" / "comment.md").exists() and not (tmp_path / "github.env").exists()


def test_the_frame_step_writes_the_issue_and_the_prompt_for_real_from_the_trusted_src(tmp_path):
    frame = next(s for s in steps() if s["name"].startswith("Frame the issue"))
    event = _decision_and_branch(tmp_path)
    (tmp_path / "event.json").write_text(json.dumps(event))
    (tmp_path / ".sdlc" / "comments.json").write_text("[]")
    (tmp_path / ".sdlc" / "pr-comments.json").write_text("[]")
    run = _shell(frame["run"], tmp_path, {"GITHUB_EVENT_PATH": str(tmp_path / "event.json")})
    assert run.returncode == 0, run.stderr
    assert (tmp_path / ".sdlc" / "issue.md").is_file() and (tmp_path / ".sdlc" / "prompt.md").is_file()


def test_a_planted_jobscan_package_in_the_workspace_is_not_imported_by_the_pre_agent_helpers(tmp_path):
    # `python -P` keeps the working directory off sys.path. Without it, this file would shadow the trusted package.
    skip = next(s for s in steps() if s["name"] == SKIP_STEP)
    (tmp_path / "jobscan").mkdir()
    (tmp_path / "jobscan" / "__init__.py").write_text("raise SystemExit('the workspace copy was imported')\n")
    _decision_and_branch(tmp_path, stage_file="spec.md")
    run = _shell(skip["run"], tmp_path, {})
    assert run.returncode == 0, run.stderr
    assert "shadow" not in run.stderr and (tmp_path / ".sdlc" / "comment.md").exists()
