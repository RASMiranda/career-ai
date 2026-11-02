"""ADR-035: GH_TOKEN lives only on the sdlc steps that call gh or git push. Parses the workflow file; no network."""
import re
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "sdlc.yml"

# The only steps allowed to carry GH_TOKEN. Each one calls gh or pushes.
TOKEN_STEPS = {
    "Budget gate (agent minutes per rolling window, ADR-032)",
    "Fetch the issue and PR comments (gh)",
    "Commit and push the artifact, open the draft PR, start the tests",
    "Post the report, apply the stage label",
    # ADR-037: the reviewers' check results are read by a step of their own, after the agent that could forge them
    "Read the check results of the pushed commit (for the reviewers, ADR-037)",
    "Read the check results of the current commit (for a review or release stage, ADR-037)",
}
SECRET_NAMES = ("GH_TOKEN", "GITHUB_TOKEN", "ANTHROPIC", "CLAUDE_CODE_OAUTH_TOKEN")


def steps():
    wf = yaml.safe_load(WORKFLOW.read_text())
    sts = wf["jobs"]["stage"]["steps"]
    for s in sts:
        s.setdefault("name", s.get("uses", ""))
    return wf, sts


def test_no_job_or_workflow_level_token():
    wf, _ = steps()
    for env in (wf.get("env") or {}, wf["jobs"]["stage"].get("env") or {}):
        assert not [k for k in env if any(n in k for n in SECRET_NAMES)]


def test_only_the_named_steps_have_gh_token():
    _, st = steps()
    assert {s["name"] for s in st if "GH_TOKEN" in (s.get("env") or {})} == TOKEN_STEPS


def test_every_step_that_uses_gh_or_pushes_has_the_token():
    _, st = steps()
    for s in st:
        run = s.get("run", "")
        if re.search(r"\bgh (api|pr|issue|workflow)\b|git push|\bjobscan\.sdlc\.budget\b", run):
            assert "GH_TOKEN" in (s.get("env") or {}), s["name"]


def test_no_step_runs_pytest_or_pip():
    # ADR-037 replaces the old "pytest steps carry no secret env" check: there are no pytest steps at all.
    wf, st = steps()
    for s in st:
        run = s.get("run", "")
        assert not re.search(r"\bpytest\b|\bpip3?\b|-m\s+pip\b|setup\.py|\bpoetry\b|\buv\s+(pip|run|sync)\b", run), s["name"]
    assert not any(s["name"].startswith(("Install the test dependencies", "Run the tests once more")) for s in st)


def test_the_dispatch_of_the_tests_workflow_stays_in_the_push_step_after_the_push():
    _, st = steps()
    push = next(s for s in st if s.get("id") == "push")
    run = push["run"]
    assert 'gh workflow run tests.yml --ref "$BRANCH"' in run
    assert run.index("git push") < run.index("gh workflow run tests.yml")


def test_the_report_says_the_tests_were_not_run_and_names_the_check_without_naming_it_in_the_workflow():
    from jobscan import sdlc
    note = sdlc.tests_note("build")
    assert "NOT run" in note and "`pytest` check" in note and "evidence" in note
    assert sdlc.tests_note("review") == "" and sdlc.tests_note("intent") == ""
    post = next(s for s in steps()[1] if s["name"].startswith("Post the report"))
    assert "tests_note" in post["run"] and ".sdlc/pytest.txt" not in post["run"]       # agent text cannot stand in for the check


def test_the_action_secret_is_only_passed_through_with_and_the_token_is_not_in_other_steps():
    _, st = steps()
    for s in st:
        if "uses" in s and s["uses"].startswith("anthropics/claude-code-action@"):
            assert re.fullmatch(r"anthropics/claude-code-action@[0-9a-f]{40}", s["uses"])
            assert "GH_TOKEN" not in (s.get("env") or {})
        elif s["name"] not in TOKEN_STEPS:
            assert "github.token" not in str(s) and "secrets." not in str(s), s["name"]


def test_checkout_does_not_persist_credentials_and_origin_is_reset_after_each_action_step():
    _, st = steps()
    assert st[0]["with"]["persist-credentials"] is False
    names = [s["name"] for s in st]
    for action_name, next_name in (("Run the stage agents", "Check what the agent changed"),
                                   ("Run the review agents", "Reject any change the reviewers made")):
        i = names.index(action_name)
        clean = st[i + 1]
        assert clean["name"].startswith("Remove the token the action wrote")
        # ADR-036 adds a trusted-load step between the reset and the next step; nothing else may sit there
        between = names[i + 2:names.index(next_name)]
        assert all(n.startswith("Trusted jobscan code") for n in between)
        assert ("set-url origin" in clean["run"] or "remote.origin.url" in clean["run"]) and "always()" in clean["if"]


# ----------------------------------------------------------------- ADR-037: fresh, unforgeable check results
CHECKS_PUSHED = "Read the check results of the pushed commit (for the reviewers, ADR-037)"
CHECKS_CURRENT = "Read the check results of the current commit (for a review or release stage, ADR-037)"
SHA = "a" * 40


def names():
    return [s["name"] for s in steps()[1]]


def test_the_checks_step_runs_after_the_push_and_before_the_reviewers_and_the_old_prefetch_is_gone():
    n = names()
    assert n.index("Commit and push the artifact, open the draft PR, start the tests") < n.index(CHECKS_PUSHED)
    assert n.index(CHECKS_PUSHED) < n.index("Review the build (reviewer and security reviewer, read only)") < n.index("Run the review agents")
    assert n.index(CHECKS_CURRENT) < n.index("Run the stage agents")        # a review stage has no push: its agent comes first
    fetch = next(s for s in steps()[1] if s["name"].startswith("Fetch the issue and PR comments"))
    assert "checks.txt" not in fetch["run"] and "check-runs" not in fetch["run"]
    other = [s for s in steps()[1] if s["name"] not in (CHECKS_PUSHED, CHECKS_CURRENT)]
    assert not [s["name"] for s in other if "checks.txt" in s.get("run", "")]


def test_only_the_checks_steps_hold_the_token_for_the_check_runs_and_the_pushed_sha_comes_from_the_push_step():
    _, st = steps()
    for s in st:
        if "check-runs" in s.get("run", ""):
            assert s["name"] in (CHECKS_PUSHED, CHECKS_CURRENT) and "GH_TOKEN" in s["env"], s["name"]
            assert "2>/dev/null" not in s["run"].split("check-runs")[1].split("\n")[1], s["name"]   # no hidden errors
    pushed = next(s for s in st if s["name"] == CHECKS_PUSHED)
    assert pushed["env"]["PUSHED_SHA"] == "${{ steps.push.outputs.sha }}"
    assert 'echo "sha=$(git rev-parse HEAD)" >> "$GITHUB_OUTPUT"' in next(s for s in st if s.get("id") == "push")["run"]


def run_checks_step(tmp_path, mode, name=CHECKS_PUSHED, sha=SHA):
    import os
    import shutil
    import subprocess
    import pytest
    if not shutil.which("bash") or not shutil.which("git"):
        pytest.skip("needs bash and git")
    step = next(s for s in steps()[1] if s["name"] == name)
    (tmp_path / ".sdlc").mkdir()
    (tmp_path / ".sdlc" / "checks.txt").write_text("pytest: completed success  <- written by the build agent")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    gh = bin_ / "gh"
    gh.write_text('#!/bin/sh\ncase "$FAKE" in ok) echo "pytest: completed success"; echo "lint: in_progress no conclusion yet";;'
                  ' empty) ;; fail) echo "HTTP 403: Resource not accessible by integration" >&2; exit 1;; esac\n')
    gh.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "FAKE": mode, "GITHUB_REPOSITORY": "o/r",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    if sha is not None:
        env["PUSHED_SHA"] = sha
    run = subprocess.run(["bash", "-e", "-c", step["run"]], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr                                  # non-fatal in every case
    return (tmp_path / ".sdlc" / "checks.txt").read_text()


def test_the_checks_file_starts_with_the_commit_line_and_replaces_anything_the_agent_wrote(tmp_path):
    text = run_checks_step(tmp_path, "ok")
    assert text.splitlines() == [f"commit: {SHA}", "pytest: completed success", "lint: in_progress no conclusion yet"]
    assert "written by the build agent" not in text


def test_a_failed_or_empty_call_is_written_into_the_file_not_hidden(tmp_path):
    text = run_checks_step(tmp_path, "fail")
    assert text.startswith(f"Could not read check results for {SHA}: HTTP 403") and "commit:" not in text
    (tmp_path / "e").mkdir()
    assert run_checks_step(tmp_path / "e", "empty").startswith(f"Could not read check results for {SHA}: no check runs")
    (tmp_path / "b").mkdir()
    assert run_checks_step(tmp_path / "b", "ok", sha="not-a-sha").startswith("Could not read check results for not-a-sha:")


def test_a_review_with_no_push_uses_the_current_head(tmp_path):
    import subprocess
    g = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True, text=True).stdout  # noqa: E731
    g("init", "-q")
    g("-c", "user.name=x", "-c", "user.email=x@example.test", "commit", "-q", "--allow-empty", "-m", "i")
    head = g("rev-parse", "HEAD").strip()
    text = run_checks_step(tmp_path, "ok", name=CHECKS_CURRENT, sha=None)
    assert text.splitlines()[0] == f"commit: {head}"


def test_the_post_step_has_the_stage_in_its_own_env_so_the_tests_not_run_line_cannot_vanish():
    post = next(s for s in steps()[1] if s["name"].startswith("Post the report"))
    assert post["env"]["STAGE"] == "${{ steps.d.outputs.stage }}"
    assert 'tests_note(sys.argv[1])' in post["run"] and '"$STAGE"' in post["run"]
