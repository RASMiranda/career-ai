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
