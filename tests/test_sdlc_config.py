"""The agentic SDLC's controls are files; these tests keep them from being quietly loosened."""

import json
import re
from pathlib import Path

import pytest
import yaml

from jobscan import sdlc

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
LABELS = {l["name"] for l in json.loads((ROOT / ".github/labels.json").read_text())}


def workflow(name):
    return yaml.safe_load((WF / f"{name}.yml").read_text())


def steps(name):
    return [s for job in workflow(name)["jobs"].values() for s in job["steps"]]


def on(name):
    d = workflow(name)
    return d.get("on", d.get(True))                      # PyYAML reads a bare `on:` key as True


# -------------------------------------------------------------------- workflows
def test_the_sdlc_workflow_starts_only_on_issues_opened_or_labelled():
    triggers = on("sdlc")
    assert set(triggers) == {"issues"} and set(triggers["issues"]["types"]) == {"opened", "labeled"}


@pytest.mark.parametrize("name", ["sdlc", "labels", "tests"])
def test_no_workflow_uses_a_trigger_that_runs_untrusted_code_with_secrets(name):
    triggers = on(name)
    triggers = set(triggers) if isinstance(triggers, (dict, list)) else {triggers}
    assert not triggers & {"pull_request_target", "issue_comment", "workflow_run", "pull_request_review_comment"}


def test_permissions_start_empty_and_are_granted_per_job_without_admin():
    wf = workflow("sdlc")
    assert wf["permissions"] == {}
    granted = wf["jobs"]["stage"]["permissions"]
    assert set(granted) == {"contents", "issues", "pull-requests", "actions", "id-token"}
    assert set(granted.values()) <= {"write"}
    assert workflow("labels")["permissions"] == {"issues": "write", "contents": "read"}


def test_untrusted_github_context_never_appears_inside_a_run_script():
    """Titles and bodies reach scripts only through env vars, never by `${{ }}` interpolation into shell."""
    for s in steps("sdlc"):
        if "run" in s:
            assert "${{" not in s["run"], s.get("name")
    risky = re.compile(r"github\.event\.(issue|comment|pull_request|label)\.(title|body|name)|head_ref")
    for s in steps("sdlc"):
        for key, value in (s.get("with") or {}).items():
            assert not risky.search(str(value)), (s.get("name"), key)


def test_the_checkout_leaves_no_token_for_the_agent_to_read():
    first = steps("sdlc")[0]
    assert first["uses"].startswith("actions/checkout@") and first["with"]["persist-credentials"] is False


def test_agents_run_with_no_web_and_no_push_or_github_tools():
    runs = [s for s in steps("sdlc") if str(s.get("uses", "")).startswith("anthropics/claude-code-action@")]
    assert len(runs) == 2                                              # the stage agents and the post-build review
    for s in runs:
        args = s["with"]["claude_args"]
        assert "--disallowedTools" in args and "WebFetch" in args and "WebSearch" in args
        assert "--allowedTools" in args
    given = [re.search(r'--allowedTools "([^"]*)"', s["with"]["claude_args"]).group(1) for s in runs]
    allowed = " ".join(given + [sdlc.STAGES[x]["tools"] for x in sdlc.STAGES])
    for banned in ("gh ", "git push", "git commit", "curl", "wget", "ssh", "WebFetch", "WebSearch", "Bash(*)", "Bash)"):
        assert banned not in allowed, banned
    assert not re.search(r"(^|,)Bash(,|$)", allowed)                   # never a bare, unrestricted Bash


def test_only_the_workflow_pushes_and_never_to_main_or_with_force():
    pushes = [s["run"] for s in steps("sdlc") if "git push" in s.get("run", "")]
    assert len(pushes) == 1
    assert 'HEAD:refs/heads/$BRANCH' in pushes[0] and "--force" not in pushes[0] and "main" not in pushes[0].split("git push")[1].split("\n")[0]
    assert all("gh pr merge" not in s.get("run", "") for s in steps("sdlc"))


def test_the_check_runs_before_anything_is_committed_and_the_review_cannot_change_files():
    names = [s.get("name", "") for s in steps("sdlc")]
    assert names.index("Check what the agent changed") < names.index("Commit and push the artifact, open the draft PR, start the tests")
    reject = next(s for s in steps("sdlc") if s.get("name") == "Reject any change the reviewers made")
    assert "check --as review" in reject["run"]


def test_agent_branches_start_the_tests_workflow_explicitly():
    assert "workflow_dispatch" in on("tests")
    push = next(s for s in steps("sdlc") if s.get("id") == "push")
    assert "gh workflow run tests.yml" in push["run"]


# ----------------------------------------------------------------------- labels
def test_every_label_the_workflow_and_forms_use_exists():
    needed = set(sdlc.LABEL_TO_STAGE) | {f"stage:{s}" for s in ("intake", "intent", "spec", "plan", "build", "review", "release")}
    needed |= sdlc.REQUESTABLE_LABELS | {"type:bug", "type:feature", "type:support"}
    assert needed <= LABELS, needed - LABELS
    for form in (ROOT / ".github/ISSUE_TEMPLATE").glob("*.yml"):
        d = yaml.safe_load(form.read_text())
        assert set(d.get("labels", [])) <= LABELS, form.name


def test_the_workflow_only_applies_labels_agents_are_allowed_to_ask_for():
    post = next(s for s in steps("sdlc") if s.get("name", "").startswith("Post the report"))["run"]
    allowed = set(re.search(r"case \"\$l\" in ([^)]*)\)", post).group(1).split("|"))
    assert allowed == sdlc.REQUESTABLE_LABELS


# ------------------------------------------------------------------ issue forms
@pytest.mark.parametrize("name", ["bug", "feature", "support"])
def test_issue_forms_warn_about_the_public_repo_and_require_the_privacy_tick(name):
    d = yaml.safe_load((ROOT / f".github/ISSUE_TEMPLATE/{name}.yml").read_text())
    assert "stage:intake" in d["labels"] and d["title"] and d["description"]
    assert "public" in d["body"][0]["attributes"]["value"].lower()
    ids = [b["id"] for b in d["body"] if "id" in b]
    assert len(ids) == len(set(ids)) and "context" in ids and "privacy" in ids
    privacy = next(b for b in d["body"] if b.get("id") == "privacy")
    assert all(o["required"] for o in privacy["attributes"]["options"])


def test_blank_issues_are_off_so_every_issue_goes_through_a_form():
    assert yaml.safe_load((ROOT / ".github/ISSUE_TEMPLATE/config.yml").read_text())["blank_issues_enabled"] is False


# ----------------------------------------------------------------------- agents
AGENTS = {p.stem: p for p in (ROOT / ".claude/agents").glob("*.md")}


def front(path):
    text = path.read_text()
    meta = yaml.safe_load(text.split("---")[1])
    return meta


def test_every_role_the_workflow_uses_has_an_agent_and_the_requested_roles_exist():
    used = {r for spec in sdlc.STAGES.values() for r in spec["roles"]}
    assert used <= set(AGENTS), used - set(AGENTS)
    assert {"stakeholder", "product-owner", "scrum-master", "tech-lead", "developer", "tester",
            "l1-support", "l2-support", "l3-support", "reviewer", "release-manager"} <= set(AGENTS)


@pytest.mark.parametrize("name", sorted(AGENTS))
def test_agent_files_are_well_formed_and_never_get_the_web(name):
    meta = front(AGENTS[name])
    assert meta["name"] == name and len(meta["description"]) > 20
    tools = {t.strip() for t in meta["tools"].split(",")}
    assert tools <= {"Read", "Grep", "Glob", "Edit", "Write", "Bash"}, tools
    assert not tools & {"WebFetch", "WebSearch"}


def test_roles_that_judge_or_support_cannot_edit_the_repository():
    for name in ("reviewer", "security-reviewer", "l1-support", "l2-support", "release-manager", "stakeholder"):
        tools = {t.strip() for t in front(AGENTS[name])["tools"].split(",")}
        assert not tools & {"Edit", "Write"}, name


def test_codeowners_cover_the_governance_paths():
    text = (ROOT / ".github/CODEOWNERS").read_text()
    for path in (".github/", ".claude/", "CLAUDE.md", "REVIEW.md", "docs/DECISIONS.md"):
        assert re.search(rf"^/{re.escape(path)}\s+@\S+", text, re.M), path


def test_the_protected_list_covers_what_adr_024_reserves_for_the_owner():
    for path in (".github/workflows/sdlc.yml", ".claude/settings.json", "scripts/hooks/guard.py", "CLAUDE.md",
                 "REVIEW.md", "routine-prompt.md", "docs/managed-settings.example.json"):
        assert sdlc.matches(path, sdlc.PROTECTED), path
    assert ".sdlc/" in (ROOT / ".gitignore").read_text()
