"""career-ai's own SDLC files: the caller, the labels and forms, the agents, the settings, CODEOWNERS.

The engine and its stage workflow live in RASMiranda/sdlc-engine (ADR-083); its tests run there against a fixture project.
These tests keep THIS repository's files from being quietly loosened. They read files only (no engine import, no
network), so `python -m pytest -q` needs nothing installed beyond requirements.txt. Whether the files fit the pinned engine
is `python -m sdlc_engine check-project --root .`, run by tests.yml."""

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
CONFIG = json.loads((ROOT / ".github/sdlc-config.json").read_text())
LABELS = {l["name"] for l in json.loads((ROOT / ".github/labels.json").read_text())}
SETTINGS = json.loads((ROOT / ".claude/settings.json").read_text())["permissions"]
STAGES = CONFIG["stages"]


def workflow(name):
    return yaml.safe_load((WF / f"{name}.yml").read_text())


def on(name):
    d = workflow(name)
    return d.get("on", d.get(True))                      # PyYAML reads a bare `on:` key as True


def matches(path, patterns):
    """The subset of path patterns the protected list uses: `dir/**`, `**/name`, a plain path, `name*.ext`."""
    for p in patterns:
        if p.endswith("/**") and path.startswith(p[:-2]):
            return True
        if p.startswith("**/") and (path == p[3:] or path.endswith("/" + p[3:])):
            return True
        if "*" not in p and path == p:
            return True
        if "*" in p and not p.startswith("**/") and not p.endswith("/**") and re.fullmatch(p.replace(".", r"\.").replace("*", "[^/]*"), path):
            return True
    return False


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


def test_the_proc_read_deny_is_in_the_project_settings_and_on_both_agent_steps():
    # The agent steps' own --disallowedTools are in the engine's stage workflow (tested there); the project settings are here.
    assert "Read(//proc/**)" in SETTINGS["deny"]                             # `//path` = absolute path from the filesystem root


def test_the_agent_cannot_read_the_checkout_git_dir_and_file_reads_stay_in_the_workspace():
    """ADR-051: the action writes its token into .git/config before the agent starts, and a bare Read, Grep or Glob could
    read it. The deny is in the project settings (the engine's stage workflow repeats it on its agent steps)."""
    assert "Read(**/.git/**)" in SETTINGS["deny"]
    assert SETTINGS.get("blockReadsOutsideWorkingDirectories") is True       # file tools stay inside the checkout
    assert not any(".git" in r for r in SETTINGS.get("allow", []))           # nothing re-opens it


def test_the_build_and_review_prompts_say_tests_are_written_but_not_run():
    # The engine renders the prompts (golden files in the engine's tests); the role files are this project's.
    for name in ("developer", "tester"):
        text = (ROOT / ".claude/agents" / f"{name}.md").read_text()
        assert "never run them" in text and "NOT run" in text and "`pytest` check" in text
    assert "Never run pytest" in (ROOT / ".claude/agents/reviewer.md").read_text()


def test_agent_branches_start_the_tests_workflow_explicitly():
    assert "workflow_dispatch" in on("tests")                                # the stage workflow runs `gh workflow run tests.yml`
    assert CONFIG["test"]["workflow"] == "tests.yml"


# ----------------------------------------------------------------------- labels
def test_every_label_the_workflow_and_forms_use_exists():
    needed = set(CONFIG["label_to_stage"]) | {f"stage:{s}" for s in ("intake", "intent", "spec", "plan", "build", "review", "release")}
    needed |= set(CONFIG["requestable_labels"]) | {"type:bug", "type:feature", "type:support"}
    assert needed <= LABELS, needed - LABELS
    for form in (ROOT / ".github/ISSUE_TEMPLATE").glob("*.yml"):
        d = yaml.safe_load(form.read_text())
        assert set(d.get("labels", [])) <= LABELS, form.name


def test_every_stage_the_workflow_applies_has_a_label():
    """The stage label is applied as ``stage:$STAGE`` for every stage in the config; each must exist."""
    missing = sorted(f"stage:{stage}" for stage in STAGES if f"stage:{stage}" not in LABELS)
    assert not missing, missing


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
    used = {r for spec in STAGES.values() for r in spec["roles"]}
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
        assert matches(path, CONFIG["protected_paths"]), path
    assert ".sdlc/" in (ROOT / ".gitignore").read_text()


# ---------------------------------------------------------------- token exposure
def test_project_settings_deny_the_runner_files_that_hold_credentials():
    deny = SETTINGS["deny"]
    for rule in ("Read(//proc/**)", "Read(//home/runner/.ssh/**)", "Read(//home/runner/.config/**)",
                 "Bash(git diff --no-index:*)", "Bash(git diff *--no-index*)"):
        assert rule in deny, rule
    assert not any(r in ("Read(//home/**)", "Read(//home/runner/**)", "Read") for r in deny)   # the checkout lives there


# ------------------------------------------------- the thin caller (sdlc.yml) calls the engine's stage workflow (ADR-083)
ENGINE_CALL = re.compile(r"RASMiranda/sdlc-engine/\.github/workflows/sdlc-stage\.yml@[0-9a-f]{40}")
CALLED_SECRETS = {"CLAUDE_CODE_OAUTH_TOKEN"}


def test_the_caller_has_exactly_the_triggers_it_had_on_main():
    assert on("sdlc") == {"issues": {"types": ["opened", "labeled"]}}


def test_the_caller_keeps_the_name_the_budget_gate_queries():
    assert workflow("sdlc")["name"] == "sdlc"                        # actions/workflows/sdlc.yml/runs in the engine's budget gate


def test_the_caller_has_no_steps_and_one_job_that_calls_the_stage_workflow():
    wf = workflow("sdlc")
    assert all("steps" not in job for job in wf["jobs"].values())
    assert list(wf["jobs"]) == ["stage"]
    assert ENGINE_CALL.fullmatch(wf["jobs"]["stage"]["uses"]), wf["jobs"]["stage"]["uses"]   # a full SHA, never a branch or tag


def test_the_engine_pin_is_one_sha_with_a_version_comment_and_tests_yml_reads_it_from_the_caller():
    """Single pin (ADR-083): the `uses:` line of sdlc.yml is the only place the engine version is written. Dependabot
    needs the trailing `# vX.Y.Z` comment to propose a bump; tests.yml derives the SHA from that line."""
    lines = [l for l in (WF / "sdlc.yml").read_text().splitlines() if "RASMiranda/sdlc-engine" in l and "uses:" in l]
    assert len(lines) == 1, lines
    assert re.fullmatch(r"\s*uses: RASMiranda/sdlc-engine/\.github/workflows/sdlc-stage\.yml@[0-9a-f]{40} # v\d+\.\d+\.\d+", lines[0]), lines[0]
    tests_yml = (WF / "tests.yml").read_text()
    assert not re.search(r"sdlc-engine@[0-9a-f]{40}", tests_yml)              # no second copy of the SHA
    step = next(s for s in yaml.safe_load(tests_yml)["jobs"]["pytest"]["steps"] if "check-project" in s.get("run", ""))["run"]
    assert ".github/workflows/sdlc.yml" in step and "grep" in step            # the SHA comes from the caller
    assert '{40}$' in step and "exit 1" in step                               # and a pin that is not 40 hex fails the step
    assert 'pip install "git+https://github.com/RASMiranda/sdlc-engine@$SHA"' in step
    assert step.index("unset PYTHONPATH") < step.index("python -m sdlc_engine check-project --root .")


def test_the_caller_passes_only_the_named_secrets_and_never_inherits():
    job = workflow("sdlc")["jobs"]["stage"]
    assert job["secrets"] == {"CLAUDE_CODE_OAUTH_TOKEN": "${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}"}
    assert set(job["secrets"]) == CALLED_SECRETS
    assert "inherit" not in json.dumps(job)
