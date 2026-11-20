"""ADR-065 (S1 D): the project's prompt text, its budget handle and its credential shape come from
.github/sdlc-config.json. The engine's built-in values are generic, so a config without them names no project.
No network, no git: the engine is configured in memory and restored after each test.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import sdlc_engine as sdlc
from sdlc_engine import budget, config
from sdlc_engine.config import ConfigError

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".github" / "sdlc-config.json"
ENGINE_NAMES = ("AGENT_BRANCH_PREFIX", "TRUSTED", "WORK", "LABEL_TO_STAGE", "REQUESTABLE_LABELS", "STAGES", "PROTECTED",
                "MAX_FILES", "MAX_ADDED_BYTES", "_CREDENTIAL", "SECRET_PATTERNS_EXTRA", "PROMPT")
BUDGET_NAMES = ("MIN_RUN_SECONDS", "DEFAULT_CAP_24H", "DEFAULT_CAP_7D", "MENTION")
PROJECT_WORDS = ("jobscan", "authorization.yaml", "profile.yaml", "career-data", "faillog", "apply bundle", "RASMiranda")
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
GENERIC_PROTECTED = [".github/**", "CLAUDE.md", "docs/DECISIONS.md", "docs/SDLC.md", "src/sdlc_engine/**"]


@pytest.fixture
def engine(monkeypatch):
    for name in ENGINE_NAMES:
        monkeypatch.setattr(sdlc, name, getattr(sdlc, name))
    for name in BUDGET_NAMES:
        monkeypatch.setattr(budget, name, getattr(budget, name))
    return sdlc


def labelled(label):
    return {"action": "labeled", "label": {"name": label}, "sender": {"type": "User", "login": "owner"},
            "issue": {"number": 7, "title": "Add a thing", "state": "open", "labels": [],
                      "author_association": "OWNER", "user": {"login": "owner"}}}


def every_prompt():
    """The prompt of every stage, rendered with whatever values the engine holds now."""
    return "\n".join(sdlc.render_prompt(sdlc.decide(labelled(label), [])) for label in sdlc.LABEL_TO_STAGE)


def prose_prompts():
    """Every prompt without the line that lists the protected paths. The built-in PROTECTED list is a safety default
    that still names the owner's files (it is not prompt text, ADR-065); the prompt's own sentences are checked."""
    return "\n".join(l for l in every_prompt().splitlines() if "never writable" not in l)


def blocked_comment():
    run = {"id": 900, "status": "completed", "conclusion": "success",
           "run_started_at": "2026-11-20T00:00:00Z", "updated_at": "2026-11-20T01:01:00Z"}
    result = budget.evaluate([run], "1", NOW, 60, 240)
    assert not result["allowed"]
    return budget.render_comment(result)


def write_config(tmp_path, cfg, name="sdlc-config.json"):
    path = tmp_path / name
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


# ------------------------------------------------------------------ the built-in values are generic
def test_the_built_in_prompts_name_no_project_and_keep_the_generic_sentences(engine):
    text = prose_prompts()
    for word in PROJECT_WORDS:
        assert word not in text, word
    assert "Never touch" not in text
    assert "- Read first: CLAUDE.md, docs/SDLC.md. A conflict with an ADR" in text
    assert "Answer from README.md and docs/ if the answer is already documented" in text
    assert "(redacted: no names, emails, companies) and request the `needs-info` label" in text


def test_a_missing_config_argument_renders_the_generic_text(engine):
    sdlc.configure(config.load(None))
    budget.configure(config.load(None))
    assert sdlc.PROMPT == sdlc.PROMPT_DEFAULTS
    assert not any(word in prose_prompts() for word in PROJECT_WORDS)
    assert blocked_comment().startswith("Budget gate: used 61.0 of 60")


def test_the_built_in_credential_shapes_no_longer_include_the_project_key(engine):
    assert sdlc.SECRET_PATTERNS_EXTRA == []
    assert "x-rapidapi" not in sdlc._CREDENTIAL.pattern


# ------------------------------------------------------------------ a config with only the required keys
def test_a_config_with_only_the_required_keys_renders_no_project_text(engine, tmp_path):
    """The optional prompt block and budget handle are left out. ``protected_paths`` is a required key and is the
    project's own list, so this config uses a generic one: the sentences checked here are the ones the engine adds."""
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg.pop("prompt")
    cfg["budget"].pop("mention")
    cfg["protected_paths"] = GENERIC_PROTECTED
    path = write_config(tmp_path, cfg)
    sdlc.configure(config.load(path))
    budget.configure(config.load(path))
    text = every_prompt()
    for word in ("jobscan", "authorization.yaml", "profile.yaml", "career-data"):
        assert word not in text, word
    assert "Never touch" not in text and "faillog" not in text
    assert blocked_comment().startswith("Budget gate: used 61.0 of 60") and "@" not in blocked_comment()


# ------------------------------------------------------------------ the project's own values reach the prompt
def test_a_second_project_supplies_its_own_prompt_block(engine, tmp_path):
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg["prompt"] = {"never_touch": "`secrets.env` or any `.pem` file", "read_first": ["README.md", "docs/ARCH.md"],
                     "support_sources": "the wiki", "support_bundle": "the diagnostics export is safe"}
    cfg["budget"]["mention"] = "@someone"
    path = write_config(tmp_path, cfg)
    sdlc.configure(config.load(path))
    budget.configure(config.load(path))
    text = every_prompt()
    assert "- Never read or write personal data. Never touch `secrets.env` or any `.pem` file." in text
    assert "- Read first: README.md, docs/ARCH.md. A conflict with an ADR" in text
    assert "Answer from the wiki if the answer" in text
    assert "(redacted: no names, emails, companies; the diagnostics export is safe)" in text
    assert blocked_comment().startswith("@someone: Budget gate:")


def test_a_wrapped_read_first_line_stays_within_120_columns(engine, tmp_path):
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg["prompt"] = {"read_first": ["a" * 60, "b" * 60, "c" * 30]}
    path = write_config(tmp_path, cfg)
    sdlc.configure(config.load(path))
    lines = every_prompt().splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("- Read first:"))
    assert len(lines[first]) <= 120 and lines[first + 1].startswith("  ")


def test_empty_never_touch_and_bundle_leave_their_sentences_out(engine, tmp_path):
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg["prompt"] = {"never_touch": "", "support_bundle": ""}
    cfg["budget"]["mention"] = ""
    path = write_config(tmp_path, cfg)
    sdlc.configure(config.load(path))
    budget.configure(config.load(path))
    text = every_prompt()
    assert "Never touch" not in text and "companies)" in text
    assert blocked_comment().startswith("Budget gate:")


# ------------------------------------------------------------------ the credential shape is the config's
def test_the_project_credential_shape_is_refused_only_when_its_config_supplies_it(engine):
    path = "docs/intents/7-add-a-thing/intent.md"
    decision = sdlc.decide(labelled("agent:intent"), [])
    leaked = {path: "X-RapidAPI-Key: " + "k" * 20}
    assert sdlc.check(decision, [path], leaked) == []                  # generic built-in: no such pattern
    sdlc.configure(config.load(CONFIG))
    problems = sdlc.check(decision, [path], leaked)
    assert problems and "an added line contains a credential" in problems[0]


def test_the_config_rejects_a_prompt_block_that_is_not_an_object(tmp_path):
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg["prompt"] = "generic"
    with pytest.raises(ConfigError):
        config.load(write_config(tmp_path, cfg))
