"""ADR-068: the verifier and the round steps follow the same rules as the reviewers, and the switch is exact.

Parses the stage workflow and the docs; no network, no git, no model."""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "sdlc-stage.yml"
DOC = ROOT / "docs" / "SDLC.md"
PIN = "anthropics/claude-code-action@6b6870e649b5ff408753befeaee5fc7989d4e6a9"
REVIEW, VERIFY = "Run the review agents", "Run the verifier agent (optional, ADR-068)"
ROUNDS, PREP = "Review round cap and marker (ADR-068)", "Verifier (optional, ADR-068) build its prompt from the kept IMPORTANT findings"


def steps():
    sts = yaml.safe_load(WORKFLOW.read_text())["jobs"]["stage"]["steps"]
    for s in sts:
        s.setdefault("name", s.get("uses", ""))
    return sts


def by_name(name):
    return next(s for s in steps() if s["name"] == name)


def position(name):
    return [s["name"] for s in steps()].index(name)


def claude_args(step):
    return step["with"]["claude_args"]


def test_the_verifier_is_pinned_and_limited_like_the_reviewers_with_its_own_tools_and_turns():
    reviewers, verifier = by_name(REVIEW), by_name(VERIFY)
    assert verifier["uses"] == reviewers["uses"] == PIN
    assert verifier["with"]["claude_code_oauth_token"] == reviewers["with"]["claude_code_oauth_token"] \
        == "${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}"
    assert "--model claude-sonnet-5-5" in claude_args(verifier) and "--model claude-sonnet-5-5" in claude_args(reviewers)
    assert "--max-turns 8" in claude_args(verifier)
    tools = re.search(r'--allowedTools "([^"]*)"', claude_args(verifier)).group(1)
    assert tools == "Read,Grep,Glob" and "Write" not in tools and "Bash" not in tools
    disallowed = re.search(r'--disallowedTools "([^"]*)"', claude_args(verifier)).group(1)
    assert disallowed == re.search(r'--disallowedTools "([^"]*)"', claude_args(reviewers)).group(1)
    assert "WebFetch" in disallowed and "WebSearch" in disallowed


def test_the_verifier_carries_no_token_no_step_permission_and_no_env_of_its_own():
    verifier = by_name(VERIFY)
    # ADR-073: the verifier's one env key is the foreground setting; no token or other variable may join it
    assert set(verifier.get("env") or {}) == {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"}
    assert "permissions" not in verifier and "GH_TOKEN" not in str(verifier)
    assert "permissions" not in by_name(REVIEW) and "permissions" not in by_name(PREP)


def test_the_verifier_runs_only_when_the_engine_says_the_switch_is_on_and_the_review_ran():
    prep = by_name(PREP)["if"]
    assert "steps.rounds.outputs.verify == 'true'" in prep and "steps.rounds.outputs.blocked != 'true'" in prep
    assert "steps.push.outputs.pushed == 'true'" in prep and "env.stop != 'true'" in prep
    assert by_name(VERIFY)["if"] == "steps.verifyprep.outputs.needed == 'true'"


def test_no_if_expression_compares_the_variable_itself_because_github_compares_strings_without_case():
    # GitHub's == on strings ignores case, so "True" would switch the verifier on. Only the engine's exact test decides.
    for s in steps():
        assert "vars.SDLC_REVIEW_VERIFY" not in s.get("if", ""), s["name"]
    assert "vars.SDLC_REVIEW_VERIFY" in by_name(ROUNDS)["env"]["VERIFY_REVIEW"]


def test_the_round_step_reads_its_two_variables_and_holds_no_token():
    rounds = by_name(ROUNDS)
    assert rounds["env"] == {"PUSHED_SHA": "${{ steps.push.outputs.sha }}",
                             "MAX_REVIEW_ROUNDS": "${{ vars.SDLC_MAX_REVIEW_ROUNDS }}",
                             "VERIFY_REVIEW": "${{ vars.SDLC_REVIEW_VERIFY }}"}
    assert 'PYTHONPATH="$TRUSTED_SRC" python -P -m sdlc_engine' in rounds["run"] and "rounds" in rounds["run"]
    assert "GH_TOKEN" not in str(rounds) and "gh " not in rounds["run"]


def test_the_round_comments_are_read_by_the_token_step_after_the_build_agent_not_before_it():
    checks = by_name("Read the check results and the issue comments of the pushed commit (for the reviewers, ADR-037, ADR-068)")
    assert position("Run the stage agents") < position(checks["name"]) < position(ROUNDS)
    assert checks["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert 'repos/$GITHUB_REPOSITORY/issues/$NUMBER/comments' in checks["run"] and ".sdlc/round-comments.json" in checks["run"]
    assert "--paginate" in checks["run"] and "|| rm -f .sdlc/round-comments.json" in checks["run"]


def test_a_blocked_round_skips_the_review_and_its_diff_and_prompt_steps():
    for name in ("Review the build (reviewer and security reviewer, read only)", REVIEW):
        assert "steps.rounds.outputs.blocked != 'true'" in by_name(name)["if"], name


def test_the_verifier_is_after_the_reviewers_reload_and_before_the_reject_step_with_its_own_token_reset():
    names = [s["name"] for s in steps()]
    reload_after_reviewers = names.index("Trusted engine code, again after the reviewers (3 of 3) use it (ADR-036)")
    assert reload_after_reviewers < position(PREP) < position(VERIFY) < position("Reject any change the reviewers made")
    reset = names[position(VERIFY) + 1]
    assert reset.startswith("Remove the token the action wrote after the verifier")
    assert by_name(reset)["if"] == "always() && steps.verifyprep.outputs.needed == 'true'"
    assert "remote.origin.url" in by_name(reset)["run"] and "rm -rf .git/hooks" in by_name(reset)["run"]


def test_the_verifier_prompt_is_built_by_trusted_code_that_reads_the_reviewers_output_once():
    prep = by_name(PREP)
    assert prep["run"].count("sdlc_engine --config") == 1 and prep["run"].count("verify-prompt --review") == 1
    assert 'PYTHONPATH="$TRUSTED_SRC" python -P -m sdlc_engine' in prep["run"]
    assert "--review .sdlc/review.md --diff .sdlc/diff.patch --out .sdlc/verify-prompt.md" in prep["run"]


def test_the_reviewers_execution_file_is_copied_before_the_verifier_can_overwrite_it():
    names = [s["name"] for s in steps()]
    keep_review = names.index("Keep the review agents' execution file (ADR-055)")
    assert keep_review < position(PREP) < position(VERIFY)
    assert names.index("Keep the verifier's execution file (ADR-068)") < position("Reject any change the reviewers made")


def test_the_post_step_reads_the_verifier_answer_by_trusted_code_and_writes_the_marker_only_for_a_review_that_ran():
    post = by_name("Post the report, apply the stage label")
    assert post["env"]["REVIEW_RAN"] == "${{ steps.rounds.outputs.review }}"
    assert post["env"]["ROUND_BLOCKED"] == "${{ steps.rounds.outputs.blocked }}"
    assert post["env"]["VERIFY_RAN"] == "${{ steps.verify.outcome != 'skipped' }}"
    run = post["run"]
    assert 'verify-answer --exec .sdlc/exec-verify.json --out .sdlc/verify-answer.md' in run
    assert 'if [ "$REVIEW_RAN" = "true" ] && [ -s .sdlc/round-marker.txt ]; then cat .sdlc/round-marker.txt >> .sdlc/post.md; fi' in run
    assert run.index("round-marker.txt >> .sdlc/post.md") < run.index('gh issue comment "$NUMBER" --body-file .sdlc/post.md')
    assert 'gh issue comment "$NUMBER" --body-file .sdlc/round-cap.md || true' in run     # the cap comment never fails the job


def test_the_verifier_step_names_no_token_outside_the_action_and_its_secret_is_the_reviewers_secret():
    for s in steps():
        if str(s.get("uses", "")).startswith("anthropics/claude-code-action@"):
            continue                       # the three agent actions are the only steps that receive the secret
        assert "CLAUDE_CODE_OAUTH_TOKEN" not in str(s), s["name"]


def test_the_docs_name_both_variables_their_defaults_the_exact_switch_and_how_to_stop_reviews():
    text = DOC.read_text(encoding="utf-8")
    section = text[text.index("### The review stage (ADR-067)"):text.index("### Support tiers")]
    assert "`SDLC_MAX_REVIEW_ROUNDS`" in section and "`SDLC_REVIEW_VERIFY`" in section
    assert "default is 3" in section or "| 3 |" in section
    assert "exactly `true`" in section and "`0`" in section and "every review" in section
