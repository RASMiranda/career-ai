"""ADR-036: jobscan steps that run after an agent use the code from origin/main, not the agent's branch.
Parses the workflow file; no network, no git."""
import re
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "sdlc.yml"
SECRETS = ("GH_TOKEN", "GITHUB_TOKEN", "ANTHROPIC", "CLAUDE_CODE_OAUTH_TOKEN")
STAGE_AGENTS = "Run the stage agents"
REVIEW_AGENTS = "Run the review agents"
LOAD = "Load the trusted jobscan code"


def steps():
    wf = yaml.safe_load(WORKFLOW.read_text())
    sts = wf["jobs"]["stage"]["steps"]
    for s in sts:
        s.setdefault("name", s.get("uses", ""))
    return sts


def names():
    return [s["name"] for s in steps()]


def after(agent_name):
    return steps()[names().index(agent_name) + 1:]


def jobscan_steps(sts):
    return [s for s in sts if "jobscan" in s.get("run", "") and "python" in s.get("run", "")]


def test_every_jobscan_call_after_the_stage_agents_uses_the_trusted_copy():
    calls = jobscan_steps(after(STAGE_AGENTS))
    assert calls
    for s in calls:
        run = s["run"]
        assert 'PYTHONPATH="$TRUSTED_SRC"' in run, s["name"]
        assert "PYTHONPATH=src" not in run, s["name"]
        assert "python -P" in run, s["name"]


def test_no_jobscan_call_after_the_stage_agents_uses_src():
    for s in after(STAGE_AGENTS):
        assert "PYTHONPATH=src" not in s.get("run", ""), s["name"]


def test_the_budget_decide_and_pre_agent_steps_keep_src_because_the_checkout_is_main():
    before = names()[:names().index(STAGE_AGENTS)]
    for s in steps()[:names().index(STAGE_AGENTS)]:
        if "jobscan" in s.get("run", ""):
            assert "PYTHONPATH=src" in s["run"] or "TRUSTED_SRC" not in s["run"], s["name"]
    assert "Decide what to run" in before


def test_each_trusted_load_comes_after_its_agent_run_and_before_the_first_jobscan_call_that_needs_it():
    sts = steps()
    loads = [i for i, n in enumerate(names()) if n.startswith(LOAD)]
    assert len(loads) == 2
    first, second = loads
    assert first > names().index(STAGE_AGENTS)
    assert second > names().index(REVIEW_AGENTS)
    # the first load precedes the stage-agent check and the push step, the first steps that need it
    assert first < names().index("Check what the agent changed")
    push = [i for i, n in enumerate(names()) if n.startswith("Commit and push")][0]
    assert first < push
    # the second load precedes the reviewer check and the post step
    reject = names().index("Reject any change the reviewers made")
    post = [i for i, n in enumerate(names()) if n.startswith("Post the report")][0]
    assert names().index(REVIEW_AGENTS) < second < reject < post
    assert sts[second]["name"].startswith(LOAD)


def test_the_load_steps_have_no_token_and_read_origin_main_not_the_working_tree():
    for s in steps():
        if not s["name"].startswith(LOAD):
            continue
        assert not [k for k in (s.get("env") or {}) if any(n in k for n in SECRETS)], s["name"]
        assert "GH_TOKEN" not in str(s), s["name"]
        assert "always()" in s["if"]
        run = s["run"]
        assert re.search(r"git archive origin/main src \| tar -x -C \"\$RUNNER_TEMP/trusted\"", run), s["name"]
        assert "cp " not in run and "rsync" not in run and "git archive HEAD" not in run
        assert 'echo "TRUSTED_SRC=$RUNNER_TEMP/trusted/src" >> "$GITHUB_ENV"' in run


def test_every_token_step_after_the_stage_agents_that_imports_jobscan_runs_after_a_trusted_load():
    sts = steps()
    start = names().index(STAGE_AGENTS)
    for i, s in enumerate(sts):
        if i > start and "GH_TOKEN" in (s.get("env") or {}) and "jobscan" in s.get("run", ""):
            prior_loads = [n for n in names()[:i] if n.startswith(LOAD)]
            assert prior_loads, s["name"]
            assert 'PYTHONPATH="$TRUSTED_SRC"' in s["run"], s["name"]
