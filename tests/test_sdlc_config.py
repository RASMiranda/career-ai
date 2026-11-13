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


EVENT_FOR_PROMPTS = {"action": "labeled", "label": {"name": "agent:build"}, "sender": {"type": "User", "login": "o"},
                     "issue": {"number": 7, "title": "t", "state": "open", "labels": [], "user": {"login": "o"}}}


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


def test_no_stage_allows_pytest_pip_or_any_repo_code_and_the_action_steps_do_not_either():
    given = [re.search(r'--allowedTools "([^"]*)"', s["with"]["claude_args"]).group(1) for s in agent_steps()]
    for tools in given + [sdlc.STAGES[x]["tools"] for x in sdlc.STAGES] + [sdlc.BUILD_TOOLS, sdlc.DOC_TOOLS, sdlc.READ_TOOLS]:
        assert not re.search(r"pytest|\bpip\b|python|poetry|\buv\b|\bmake\b|\bnpm\b", tools, re.I), tools
    for x in sdlc.STAGES:                                                   # every Bash rule left is a read-only git one
        for rule in re.findall(r"Bash\(([^)]*)\)", sdlc.STAGES[x]["tools"]):
            assert rule in ("git status:*", "git diff:*", "git log:*"), (x, rule)
    assert sdlc.STAGES["build"]["tools"] == sdlc.DOC_TOOLS                  # nothing else changed for build


def test_the_proc_read_deny_is_in_the_project_settings_and_on_both_agent_steps():
    deny = json.loads((ROOT / ".claude/settings.json").read_text())["permissions"]["deny"]
    assert "Read(//proc/**)" in deny                                         # `//path` = absolute path from the filesystem root
    for s in agent_steps():
        assert "Read(//proc/**)" in re.search(r'--disallowedTools "([^"]*)"', s["with"]["claude_args"]).group(1)


def test_the_agent_cannot_read_the_checkout_git_dir_and_file_reads_stay_in_the_workspace():
    """ADR-051: the action writes its token into .git/config before the agent starts, and a bare Read, Grep or Glob could
    read it. The deny is in the project settings and, because a later stage checks out the issue branch, also on both
    agent steps. Verified on 11 Nov 2026 with a before/after probe that used a fake token."""
    permissions = json.loads((ROOT / ".claude/settings.json").read_text())["permissions"]
    assert "Read(**/.git/**)" in permissions["deny"]
    assert permissions.get("blockReadsOutsideWorkingDirectories") is True    # file tools stay inside the checkout
    assert not any(".git" in r for r in permissions.get("allow", []))        # nothing re-opens it
    for s in agent_steps():
        assert "Read(**/.git/**)" in re.search(r'--disallowedTools "([^"]*)"', s["with"]["claude_args"]).group(1)


def test_the_build_and_review_prompts_say_tests_are_written_but_not_run():
    build = sdlc.render_prompt(sdlc.decide(json.loads(json.dumps(EVENT_FOR_PROMPTS)), ["agent/7-x"]))
    assert "cannot run tests" in build and "NOT run" in build and "pytest -q" not in build
    review = sdlc.render_prompt(sdlc.as_stage(sdlc.decide(EVENT_FOR_PROMPTS, ["agent/7-x"]), "review"))
    assert "cannot run tests" in review and ".sdlc/checks.txt" in review
    for name in ("developer", "tester"):
        text = (ROOT / ".claude/agents" / f"{name}.md").read_text()
        assert "never run them" in text and "NOT run" in text and "`pytest` check" in text
    assert "Never run pytest" in (ROOT / ".claude/agents/reviewer.md").read_text()


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
    fake.write_text('#!/bin/sh\n[ "$1 $2" = "pr list" ] && { [ -n "$FAKE_PR" ] && echo "$FAKE_PR"; exit 0; }\nwhile [ $# -gt 0 ]; do [ "$1" = --body-file ] && cat "$2" >> "$POSTED"; shift; done\n')
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "POSTED": str(tmp_path / "posted.txt"),
           "NUMBER": "7", "TRIGGER_LABEL": "", "STAGE": "build", "ROLES": "[]",
           "REJECTED": "success", "BRANCH": "agent/7-x", "FAKE_PR": "",
           "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"), **env_extra}
    env.pop("blocked", None) if "blocked" not in env_extra else None
    env.pop("PYTHONPATH", None)
    env.setdefault("TRUSTED_SRC", str(tmp_path / "src"))                  # ADR-036: the post step imports jobscan from here
    subprocess.run(["bash", "-e", "-c", step["run"]], cwd=tmp_path, env=env, check=True, capture_output=True)
    return (tmp_path / "posted.txt").read_text()


FIXED = "Blocked by the safety check. See the run log."


def leaky():
    return {"comment.md": f"report {FAKE_TOKEN}", "build-report.md": f"built {FAKE_TOKEN}",
            "review.md": f"finding {FAKE_TOKEN}", "pytest.txt": f"2 passed {FAKE_TOKEN}", "labels.txt": "needs-info\n"}


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
    # ADR-037: an agent-written .sdlc/pytest.txt is no longer posted; the workflow's own line says tests were not run.
    body = run_post_step(tmp_path, {}, {"comment.md": "built it", "review.md": "Verdict: no Important findings",
                                        "pytest.txt": "12 passed"})
    assert "built it" in body and "Verdict: no Important findings" in body and "12 passed" not in body and FIXED not in body
    assert "Tests were NOT run by the agent" in body and "`pytest` check on the PR" in body
    assert "Next gate (yours)" in body


def test_the_report_names_the_open_pr_near_the_top_and_only_then(tmp_path):
    files = {"comment.md": "built it"}
    body = run_post_step(tmp_path, {"FAKE_PR": "12"}, files)
    assert body.splitlines()[1] == "PR: #12"
    (tmp_path / "b").mkdir()
    body = run_post_step(tmp_path / "b", {}, files)
    assert "PR:" not in body and "built it" in body


def test_a_blocked_run_has_no_pr_line(tmp_path):
    assert "PR:" not in run_post_step(tmp_path, {"blocked": "true", "FAKE_PR": "12"}, leaky())


# ------------------------------------------- the build report survives the reviewers (ADR-052)
def step_named(prefix):
    return next(s for s in steps("sdlc") if str(s.get("name", "")).startswith(prefix))


def test_the_build_report_is_copied_aside_before_the_review_agents_start():
    names = [s.get("name", "") for s in steps("sdlc")]
    assert names.index(step_named("Review the build")["name"]) < names.index("Run the review agents")


def test_the_copy_aside_copies_the_build_report_or_writes_a_fixed_line(tmp_path):
    import os
    import subprocess

    lines = step_named("Review the build")["run"].splitlines()
    script = "\n".join(lines[:next(i for i, l in enumerate(lines) if l.startswith("git diff"))])   # before the reviewers
    (tmp_path / ".sdlc").mkdir()
    (tmp_path / ".sdlc" / "comment.md").write_text("built it\n")
    subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, env=os.environ, check=True, capture_output=True)
    assert (tmp_path / ".sdlc" / "build-report.md").read_text() == "built it\n"
    (tmp_path / ".sdlc" / "comment.md").unlink()
    subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, env=os.environ, check=True, capture_output=True)
    assert (tmp_path / ".sdlc" / "build-report.md").read_text() == "The build agent wrote no report.\n"


def test_the_build_stage_posts_the_build_report_not_a_reviewers_comment_then_the_review_then_the_tests_note(tmp_path):
    body = run_post_step(tmp_path, {}, {"comment.md": "reviewer overwrote this", "build-report.md": "built it",
                                        "review.md": "Verdict: no Important findings"})
    assert "built it" in body and "reviewer overwrote this" not in body
    order = [body.index(p) for p in ("built it", "**Review**", sdlc.tests_note("build"), "**Next gate (yours):**")]
    assert order == sorted(order)


def test_without_a_build_report_the_stage_report_is_posted(tmp_path):
    body = run_post_step(tmp_path, {}, {"comment.md": "no push, so no review"})
    assert "no push, so no review" in body


def test_the_build_report_is_in_the_secrets_scan_and_a_fake_secret_in_it_is_flagged(tmp_path):
    import os
    import subprocess
    import sys

    assert ".sdlc/build-report.md" in sdlc.SDLC_OUTPUT
    assert sdlc.scan_problems({".sdlc/build-report.md": f"report {FAKE_TOKEN}"})
    (tmp_path / ".sdlc").mkdir()
    (tmp_path / ".sdlc" / "build-report.md").write_text(f"report {FAKE_TOKEN}\n")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    run = subprocess.run([sys.executable, "-P", "-m", "jobscan.sdlc", "scan"], cwd=tmp_path, env=env,
                         capture_output=True, text=True)
    assert run.returncode == 1 and "build-report.md" in run.stderr


def test_a_blocked_run_removes_the_build_report_so_no_agent_text_is_left_to_post(tmp_path):
    body = run_post_step(tmp_path, {"blocked": "true"}, {"build-report.md": f"built {FAKE_TOKEN}"})
    assert FIXED in body and FAKE_TOKEN not in body
    assert not (tmp_path / ".sdlc" / "build-report.md").exists()


def test_the_draft_pr_body_comes_from_the_tested_function_and_only_type_labels_are_copied():
    text = (WF / "sdlc.yml").read_text()
    assert "Refs #" not in text and "jobscan.sdlc pr-body" in text
    assert 'type:*) gh pr edit "$PR_NEW" --add-label "$l"' in text
    assert "agent:*) gh pr edit" not in text and "stage:*) gh pr edit" not in text


def test_a_stop_for_another_reason_still_posts_the_workflows_own_message(tmp_path):
    body = run_post_step(tmp_path, {"stop": "true"}, {"comment.md": "No branch for this issue yet: run the intent stage first."})
    assert "No branch for this issue yet" in body and FIXED not in body


def test_the_workflow_never_writes_agent_output_to_the_job_summary():
    # The Budget gate prints only its own numbers (ADR-032). The post step writes one line, the denial summary built
    # by trusted code from tool names and counts (ADR-055); nothing else reaches the job summary.
    text = (WF / "sdlc.yml").read_text()
    start = text.index("      - name: Budget gate")
    end = text.index("      - name: Check out the issue's branch")
    rest = (text[:start] + text[end:]).replace('cat .sdlc/denial-summary.txt >> "$GITHUB_STEP_SUMMARY"', "")
    assert "GITHUB_STEP_SUMMARY" not in rest
    assert ".sdlc/post.md" not in text[start:end]


# ------------------------------------------- the agents' execution files and last message (ADR-055)
def test_each_agent_step_has_an_id_and_its_execution_file_is_copied_right_after_the_step_before_the_post():
    # The action overwrites its execution file on every run, so each copy must run before the next agent starts.
    # The token-reset steps must stay straight after each agent (test_sdlc_token_scope), so the copies follow the
    # check (stage) and reject (review) steps, which only read the checkout.
    all_steps = steps("sdlc")
    names = [s.get("name", "") for s in all_steps]
    stage_agent, review_agent = names.index("Run the stage agents"), names.index("Run the review agents")
    assert all_steps[stage_agent]["id"] == "agent" and all_steps[review_agent]["id"] == "review"
    for step_id, keep_name, kept, previous in (
            ("agent", "Keep the stage agent's execution file (ADR-055)", "exec-stage.json", "Check what the agent changed"),
            ("review", "Keep the review agents' execution file (ADR-055)", "exec-review.json",
             "Reject any change the reviewers made")):
        k = names.index(keep_name)
        keep = all_steps[k]
        assert names[k - 1] == previous
        assert keep["if"] == "always() && steps.d.outputs.run == 'true'"
        assert keep["env"] == {"SRC": "${{ steps.%s.outputs.execution_file }}" % step_id}
        assert f".sdlc/{kept}" in keep["run"] and "${{" not in keep["run"]
    assert names.index("Keep the stage agent's execution file (ADR-055)") < review_agent
    assert names.index("Keep the review agents' execution file (ADR-055)") < names.index("Post the report, apply the stage label")


def test_the_execution_file_copies_run_only_when_the_action_wrote_one(tmp_path):
    import os
    import subprocess

    keep = next(s for s in steps("sdlc") if str(s.get("name", "")).startswith("Keep the stage agent"))
    (tmp_path / ".sdlc").mkdir()
    (tmp_path / "from-action.json").write_text('[{"type": "result"}]')
    subprocess.run(["bash", "-e", "-c", keep["run"]], cwd=tmp_path, env={**os.environ, "SRC": "from-action.json"},
                   check=True, capture_output=True)
    assert (tmp_path / ".sdlc" / "exec-stage.json").read_text() == '[{"type": "result"}]'
    for src in ("", "no-such-file.json"):
        (tmp_path / ".sdlc" / "exec-stage.json").unlink(missing_ok=True)
        subprocess.run(["bash", "-e", "-c", keep["run"]], cwd=tmp_path, env={**os.environ, "SRC": src},
                       check=True, capture_output=True)
        assert not (tmp_path / ".sdlc" / "exec-stage.json").exists()


def test_the_report_flag_is_read_from_comment_md_before_the_fallback_is_written(tmp_path):
    import os
    import subprocess

    run = step_named("Check what the agent changed")["run"]
    lines = run.splitlines()
    script = "\n".join(lines[:next(i for i, l in enumerate(lines) if "PYTHONPATH" in l)])   # before the check
    (tmp_path / ".sdlc").mkdir()
    env = {**os.environ, "GITHUB_ENV": str(tmp_path / "env.txt")}
    subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, env=env, check=True, capture_output=True)
    assert (tmp_path / "env.txt").read_text().strip() == "agent_report=false"
    (tmp_path / ".sdlc" / "comment.md").write_text("built it\n")
    subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, env=env, check=True, capture_output=True)
    assert (tmp_path / "env.txt").read_text().splitlines()[-1] == "agent_report=true"


EXEC_OK = [{"type": "assistant", "message": {"content": "work"}},
           {"type": "result", "result": "I ran out of ideas", "permission_denials": [
               {"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {"command": "echo " + FAKE_TOKEN}}]}]


def exec_file(messages):
    return {"exec-stage.json": json.dumps(messages)}


def test_a_denial_line_is_in_the_comment_and_the_summary_only_when_something_was_denied(tmp_path):
    body = run_post_step(tmp_path, {}, {"comment.md": "built it", **exec_file(EXEC_OK)})
    line = "Permission denials: stage agent 1 (Bash); reviewers 0"
    assert line in body and body.index(line) < body.index("built it")
    assert line in (tmp_path / "summary.md").read_text()
    (tmp_path / "b").mkdir()
    quiet = [{"type": "result", "result": "done", "permission_denials": []}]
    body = run_post_step(tmp_path / "b", {}, {"comment.md": "built it", **exec_file(quiet)})
    assert "Permission denials" not in body and "Permission denials: none" in (tmp_path / "b" / "summary.md").read_text()


def test_with_no_report_the_last_message_is_posted_under_its_untrusted_heading(tmp_path):
    fallback = "The stage ended without a report from the agent."
    body = run_post_step(tmp_path, {"AGENT_REPORT": "false"}, {"comment.md": fallback, **exec_file(EXEC_OK)})
    assert "**Agent's last message (untrusted, not reviewed)**" in body and "I ran out of ideas" in body
    assert body.index(fallback) < body.index("I ran out of ideas")
    assert FAKE_TOKEN not in body                                           # the tool input is never shown


def test_a_report_is_posted_without_the_last_message(tmp_path):
    body = run_post_step(tmp_path, {"AGENT_REPORT": "true"}, {"comment.md": "built it", **exec_file(EXEC_OK)})
    assert "Agent's last message" not in body and "I ran out of ideas" not in body


def test_a_fake_token_in_the_last_message_is_withheld_from_the_comment(tmp_path):
    messages = [{"type": "result", "result": f"I used {FAKE_TOKEN}", "permission_denials": []}]
    body = run_post_step(tmp_path, {"AGENT_REPORT": "false"}, {"comment.md": "x", **exec_file(messages)})
    assert "withheld by the safety check" in body and FAKE_TOKEN not in body and "I used" not in body


def test_a_blocked_run_posts_neither_the_denial_line_nor_the_last_message_and_removes_the_execution_files(tmp_path):
    files = {**leaky(), **exec_file(EXEC_OK)}
    body = run_post_step(tmp_path, {"blocked": "true", "AGENT_REPORT": "false"}, files)
    assert FIXED in body and "Permission denials" not in body and "Agent's last message" not in body
    assert FAKE_TOKEN not in body and "I ran out of ideas" not in body
    assert not (tmp_path / ".sdlc" / "exec-stage.json").exists()
    assert not (tmp_path / ".sdlc" / "agent-message.md").exists()
    assert "Permission denials: stage agent 1 (Bash)" in (tmp_path / "summary.md").read_text()   # names only, job summary


def test_the_execution_files_themselves_are_never_scanned_or_posted_and_tool_input_never_appears(tmp_path):
    body = run_post_step(tmp_path, {}, {"comment.md": "built it", **exec_file(EXEC_OK)})
    summary = (tmp_path / "summary.md").read_text()
    assert FAKE_TOKEN not in body and FAKE_TOKEN not in summary and "tool_input" not in body + summary


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
