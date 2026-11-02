"""ADR-036: jobscan steps that run after an agent use the code from the trigger commit, not the agent's branch.
Parses the workflow file; no network, no git."""
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "sdlc.yml"
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


def test_pre_agent_steps_keep_src_because_the_checkout_is_the_trigger_commit():
    before = steps()[:names().index(STAGE_AGENTS)]
    assert any("PYTHONPATH=src" in s.get("run", "") for s in before)


def test_the_trusted_code_is_a_second_checkout_pinned_to_the_trigger_commit_and_never_git_archive():
    text = WORKFLOW.read_text()
    assert "git archive" not in text
    checkouts = [s for s in steps() if s["name"].startswith(LOAD) and "uses" in s]
    assert len(checkouts) == 2
    for s in checkouts:
        assert s["uses"] == "actions/checkout@v4"
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
