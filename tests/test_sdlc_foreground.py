"""ADR-073: stage agents run their subagents in the foreground. Two layers, both pinned here:
the environment setting on every claude-code-action step (checked on the workflow YAML), and one bullet in the shared
stage prompt (checked on the prompt each of the nine stages renders). No network, no git."""
from pathlib import Path

import pytest
import yaml

import sdlc_engine as sdlc
from test_sdlc_golden import configured, _stage_decisions  # noqa: F401  (configured is a fixture)

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = [ROOT / ".github" / "workflows" / "sdlc.yml", ROOT / ".github" / "workflows" / "sdlc-stage.yml"]
ACTION = "anthropics/claude-code-action@"
SETTING = {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"}
FOREGROUND = ("- Run each subagent in the foreground, one at a time, and wait for its result before you continue; never "
              "start one in the background and never end your turn while one is still running, because an ended turn "
              "ends the stage and nothing it was still doing is kept. If a subagent returns nothing, write that role's "
              "part yourself.")


def action_steps():
    out = []
    for path in WORKFLOWS:
        for job in yaml.safe_load(path.read_text())["jobs"].values():
            out += [s for s in job.get("steps", []) if str(s.get("uses", "")).startswith(ACTION)]
    return out


def test_there_are_three_agent_actions_and_each_sets_the_setting_to_one_and_nothing_else():
    steps = action_steps()
    assert len(steps) == 3          # the stage agents, the review agents, the verifier (ADR-068)
    for s in steps:
        assert s.get("env") == SETTING, s.get("name")   # exact: no other key, and the value is the string "1"


def test_the_setting_is_not_a_secret_and_no_action_step_passes_a_token_in_its_env():
    for s in action_steps():
        assert not [k for k in s["env"] if "TOKEN" in k or "KEY" in k or "SECRET" in k], s["name"]


def test_every_stage_prompt_carries_the_foreground_rule_right_after_the_subagent_line(configured):
    decisions = _stage_decisions()
    assert set(decisions) == set(sdlc.STAGES) and len(decisions) == 9
    for stage, decision in decisions.items():
        lines = sdlc.render_prompt(decision).splitlines()
        assert FOREGROUND in lines, stage
        i = lines.index(FOREGROUND)
        assert lines[i - 1].startswith("- Use the subagents named below"), stage
