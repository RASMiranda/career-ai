"""ADR-060, ADR-083: this project's values for the SDLC engine live in .github/sdlc-config.json.

The engine reads the file from the trigger commit (its own tests cover loading, validation and the rules, against a
fixture project). Here the file's own values are pinned, so a change to one of them is a deliberate edit of this test,
and the values that also appear in tests.yml are kept equal. `python -m sdlc_engine check-project --root .` (tests.yml)
checks the shape against the pinned engine. Files only: no engine import, no network, no git.
"""
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".github" / "sdlc-config.json"
TESTS_WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
RAPIDAPI_PATTERN = r"x-rapidapi-key\s*[:=]\s*\w{16,}"      # the project's own credential shape (ADR-065)
READ = "Read,Grep,Glob,Write,Bash(git status:*),Bash(git diff:*),Bash(git log:*)"
DOC = "Read,Grep,Glob,Write,Edit,Bash(git status:*),Bash(git diff:*),Bash(git log:*)"
N = "docs/intents/{n}-{slug}"
# stage: (roles, needs, writes, repo, tools, turns); checkout is only set on review and release
STAGES = {
    "intent": (["stakeholder", "product-owner"], None, [f"{N}/intent.md"], True, DOC, 12),
    "spec": (["product-owner", "stakeholder"], "intent.md", [f"{N}/spec.md"], True, DOC, 20),
    "plan": (["tech-lead", "scrum-master"], "spec.md", [f"{N}/plan.md"], True, DOC, 25),
    "build": (["tester", "developer"], "plan.md", ["src/**", "tests/**", "docs/**", "README.md"], True, DOC, 60),
    "review": (["reviewer", "security-reviewer"], None, [], False, READ, 15),
    "release": (["release-manager"], None, [], False, READ, 10),
    "support-l1": (["l1-support"], None, [], False, READ, 10),
    "support-l2": (["l2-support"], None, [], False, READ, 15),
    "support-l3": (["l3-support", "tech-lead"], None, [f"{N}/intent.md", "docs/incidents/*.md"], True, DOC, 20),
}
PROTECTED = [".github/**", ".claude/**", "CLAUDE.md", "REVIEW.md", "routine-prompt.md", "docs/DECISIONS.md",
             "docs/SDLC.md", "docs/managed-settings.example.json", "pyproject.toml", "requirements*.txt",
             "**/profile.yaml", "**/config.yaml", "**/authorization*.yaml", "**/.env*", "scripts/**", ".gitignore"]


def cfg():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def test_the_file_holds_the_projects_values_and_the_project_text_the_engines_defaults_leave_out():
    """The values are the ones the engine's built-ins held before the extraction (S3 step h), so nothing changed. The
    project text, the owner's handle and the project's credential shape (ADR-065) are supplied only by this file."""
    c = cfg()
    assert c["config_version"] == 1
    assert c["default_branch"] == "main" and c["agent_branch_prefix"] == "agent/"
    assert c["artifact_dir"] == "docs/intents/{n}-{slug}"
    assert c["trusted_associations"] == ["OWNER", "MEMBER", "COLLABORATOR"]
    assert c["label_to_stage"] == {
        "agent:intent": "intent", "agent:spec": "spec", "agent:plan": "plan", "agent:build": "build",
        "agent:review": "review", "agent:release": "release", "agent:support": "support-l1",
        "agent:l2": "support-l2", "agent:l3": "support-l3"}
    assert c["requestable_labels"] == ["needs-info", "support:L2", "support:L3", "type:bug", "type:feature"]
    assert set(c["stages"]) == set(STAGES)
    for name, (roles, needs, writes, repo, tools, turns) in STAGES.items():
        s = c["stages"][name]
        assert (s["roles"], s["needs"], s["writes"], s["repo"], s["tools"], s["turns"]) == (roles, needs, writes, repo, tools, turns), name
        assert s.get("checkout", False) is (name in ("review", "release")), name
    assert c["protected_paths"] == PROTECTED              # in full; the engine's folder left in S3 step h, so its entry is gone
    assert "src/sdlc_engine/**" not in c["protected_paths"]
    assert not any((ROOT / d).exists() for d in ("src/sdlc_engine", "engine", "project-config"))   # `engine/` and `project-config/` are the stage workflow's
    assert c["limits"] == {"max_files": 60, "max_added_bytes": 400000}
    assert c["budget"] == {"cap_24h": 60, "cap_7d": 240, "min_run_seconds": 30, "mention": "@RASMiranda"}
    assert c["secret_patterns_extra"] == [RAPIDAPI_PATTERN]
    assert c["prompt"] == {
        "never_touch": "`authorization.yaml`, any `profile.yaml`, or `career-data`",
        "read_first": ["CLAUDE.md", "docs/SDLC.md", "docs/PRODUCT.md",
                       "docs/DECISIONS.md (ADR-003, ADR-007, ADR-017 to ADR-022)", "docs/REFERENCE-AIAPPLY.md"],
        "support_sources": "README.md, docs/ and the failure explanations in src/jobscan/apply/faillog.py",
        "support_bundle": "`python -m jobscan.apply bundle` output is safe"}
    assert c["model"] == "claude-sonnet-5-5" and c["runner"] == "ubuntu-24.04"
    assert c["commit_title"] == "[#$NUMBER] sdlc: $STAGE" and c["pr_title"] == "[#$NUMBER] $ISSUE_TITLE"


def test_the_credential_regex_the_file_builds_is_the_pinned_one():
    extra = cfg()["secret_patterns_extra"]
    assert extra == [RAPIDAPI_PATTERN]
    rx = re.compile("|".join(extra), re.I)                                   # the engine matches extras case-insensitively
    assert rx.search("X-RapidAPI-Key: " + "a1b2c3d4" * 3) and not rx.search("x-rapidapi-key: short")


def test_every_stage_output_under_the_artifact_dir_starts_with_it():
    c = cfg()
    for name, stage in c["stages"].items():
        for path in stage["writes"]:
            if "{n}" in path:
                assert path.startswith(c["artifact_dir"] + "/"), (name, path)


def test_the_values_the_yaml_holds_match_the_file():
    """YAML cannot read JSON, so these values stay in tests.yml. The engine's stage workflow holds the rest (the model,
    the titles, the base branch): they match this file today, and the engine's own tests keep them equal to its fixture."""
    c = cfg()
    tests_yml = TESTS_WORKFLOW.read_text()
    assert f"runs-on: {c['runner']}" in tests_yml
    test = c["test"]
    assert f'python-version: "{test["python"]}"' in tests_yml
    assert f"- run: {test['command']}" in tests_yml
    assert re.search(rf"^  {re.escape(test['check_name'])}:$", tests_yml, re.M)
    assert (ROOT / ".github" / "workflows" / test["workflow"]).is_file()
    assert set(c["git_identity"]) == {"name", "email"}
    on = yaml.safe_load(tests_yml); on = on.get("on", on.get(True))      # PyYAML reads a bare `on:` key as True
    assert "workflow_dispatch" in on       # the stage workflow dispatches it on agent branches


def test_the_file_the_engine_reads_is_in_the_repository_root_config_dir():
    assert CONFIG.is_file() and isinstance(cfg(), dict) and cfg()["config_version"] == 1
