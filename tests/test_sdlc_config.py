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


# ---------------------------------------------------------------- token exposure
FAKE_TOKEN = "sk-ant-oat01-" + "FAKE" * 8                 # obviously fake


def agent_steps():
    return [s for s in steps("sdlc") if str(s.get("uses", "")).startswith("anthropics/claude-code-action@")]


def test_the_action_is_pinned_to_a_commit_and_does_not_set_the_subprocess_env_scrub():
    runs = agent_steps()
    assert len(runs) == 2
    for s in runs:
        assert s["uses"] == "anthropics/claude-code-action@6b6870e649b5ff408753befeaee5fc7989d4e6a9"
        # CLAUDE_CODE_SUBPROCESS_ENV_SCRUB needs bubblewrap, which the runner lacks: it failed the first run (ADR-033).
        assert "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB" not in s.get("env", {})
    assert all(re.search(r"@[0-9a-f]{40} # v1$", line.strip())
               for line in (WF / "sdlc.yml").read_text().splitlines() if "claude-code-action@" in line)


def test_project_settings_deny_the_runner_files_that_hold_credentials():
    deny = json.loads((ROOT / ".claude/settings.json").read_text())["permissions"]["deny"]
    for rule in ("Read(//proc/**)", "Read(//home/runner/.ssh/**)", "Read(//home/runner/.config/**)",
                 "Bash(git diff --no-index:*)", "Bash(git diff *--no-index*)"):
        assert rule in deny, rule
    assert not any(r in ("Read(//home/**)", "Read(//home/runner/**)", "Read") for r in deny)   # the checkout lives there


def run_post_step(tmp_path, env_extra, files):
    """Run the workflow's real post step with a fake `gh`, and return the body it would post."""
    import os
    import shutil
    import subprocess
    if not shutil.which("bash"):
        pytest.skip("needs bash")
    step = next(s for s in steps("sdlc") if str(s.get("name", "")).startswith("Post the report"))
    (tmp_path / "src").symlink_to(ROOT / "src")                            # the step runs from the repository root
    (tmp_path / ".sdlc").mkdir()
    for name, text in files.items():
        (tmp_path / ".sdlc" / name).write_text(text)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    fake = bin_ / "gh"
    fake.write_text('#!/bin/sh\nwhile [ $# -gt 0 ]; do [ "$1" = --body-file ] && cat "$2" >> "$POSTED"; shift; done\n')
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "POSTED": str(tmp_path / "posted.txt"),
           "NUMBER": "7", "TRIGGER_LABEL": "", "STAGE": "build", "ROLES": "[]",
           "REJECTED": "success", **env_extra}
    env.pop("blocked", None) if "blocked" not in env_extra else None
    env.pop("PYTHONPATH", None)
    subprocess.run(["bash", "-e", "-c", step["run"]], cwd=tmp_path, env=env, check=True, capture_output=True)
    return (tmp_path / "posted.txt").read_text()


FIXED = "Blocked by the safety check. See the run log."


def leaky():
    return {"comment.md": f"report {FAKE_TOKEN}", "review.md": f"finding {FAKE_TOKEN}", "pytest.txt": f"2 passed {FAKE_TOKEN}",
            "labels.txt": "needs-info\n"}


def test_a_blocked_run_posts_only_the_fixed_message(tmp_path):
    body = run_post_step(tmp_path, {"blocked": "true"}, leaky())
    assert FIXED in body and FAKE_TOKEN not in body and "Review" not in body and "passed" not in body


def test_a_failed_review_reject_step_also_posts_only_the_fixed_message(tmp_path):
    body = run_post_step(tmp_path, {"REJECTED": "failure"}, leaky())
    assert FIXED in body and FAKE_TOKEN not in body and "Review" not in body


def test_text_written_after_the_first_check_is_scanned_again_before_posting(tmp_path):
    body = run_post_step(tmp_path, {}, leaky())                            # no `blocked` flag: the final scan catches it
    assert FIXED in body and FAKE_TOKEN not in body


def test_a_normal_run_still_posts_the_report_review_and_test_result(tmp_path):
    body = run_post_step(tmp_path, {}, {"comment.md": "built it", "review.md": "Verdict: no Important findings",
                                        "pytest.txt": "12 passed"})
    assert "built it" in body and "Verdict: no Important findings" in body and "12 passed" in body and FIXED not in body
    assert "Next gate (yours)" in body


def test_a_stop_for_another_reason_still_posts_the_workflows_own_message(tmp_path):
    body = run_post_step(tmp_path, {"stop": "true"}, {"comment.md": "No branch for this issue yet: run the intent stage first."})
    assert "No branch for this issue yet" in body and FIXED not in body


def test_the_workflow_never_writes_agent_output_to_the_job_summary():
    # The one writer is the Budget gate, which prints only its own numbers (ADR-032), never agent text.
    text = (WF / "sdlc.yml").read_text()
    start = text.index("      - name: Budget gate")
    end = text.index("      - name: Check out the issue's branch")
    assert "GITHUB_STEP_SUMMARY" not in text[:start] + text[end:]
    assert ".sdlc/post.md" not in text[start:end]


# ------------------------------------------------------- the commit step's shell
def test_the_push_step_stages_and_commits_with_an_ignored_sdlc_dir(tmp_path):
    """Run the step's real add/commit lines in a scratch repo where .sdlc is gitignored (run 40297305744)."""
    import os
    import subprocess

    step = next(s for s in steps("sdlc") if s.get("id") == "push")
    lines = step["run"].splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("git add"))
    end = next(i for i, l in enumerate(lines) if l.strip().startswith("git push"))
    script = "\n".join(lines[start:end]) + "\nfi\n"               # up to the commit; close the if/else

    def git(*a):
        return subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True, text=True).stdout

    git("init", "-q")
    git("config", "user.name", "t")
    git("config", "user.email", "t@example.invalid")
    (tmp_path / ".gitignore").write_text(".sdlc/\n")
    (tmp_path / "tracked.txt").write_text("one\n")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    (tmp_path / "tracked.txt").write_text("two\n")
    (tmp_path / ".sdlc").mkdir()
    (tmp_path / ".sdlc" / "comment.md").write_text("x\n")

    env = {**os.environ, "NUMBER": "7", "STAGE": "intent", "GIT_CONFIG_GLOBAL": os.devnull}
    run = subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert git("show", "--name-only", "--format=", "HEAD").split() == ["tracked.txt"]
    assert not [l for l in git("ls-files").splitlines() if l.startswith(".sdlc")]
    assert git("diff", "--cached", "--name-only").strip() == ""
