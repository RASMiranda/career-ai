"""ADR-060: the sdlc engine's project values live in .github/sdlc-config.json.

These tests keep the file equal to the built-in values (a typo fails), show that no --config means the built-in values, that a
missing or malformed file stops the run instead of falling back, and that every trusted checkout fetches the file. They parse the
workflow file; no network, no git.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import sdlc_engine as sdlc
from sdlc_engine import budget, config
from sdlc_engine.config import ConfigError

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".github" / "sdlc-config.json"
WORKFLOW = ROOT / ".github" / "workflows" / "sdlc.yml"
TESTS_WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
TRUSTED_CONFIG = '--config "$TRUSTED_SRC/../.github/sdlc-config.json"'   # after the trusted copy exists
WORKSPACE_CONFIG = "--config .github/sdlc-config.json"                   # decide and budget: the trigger commit
LOAD = "Trusted jobscan code"
ENGINE_NAMES = ("AGENT_BRANCH_PREFIX", "TRUSTED", "WORK", "LABEL_TO_STAGE", "REQUESTABLE_LABELS", "STAGES", "PROTECTED",
                "MAX_FILES", "MAX_ADDED_BYTES", "_CREDENTIAL")
BUDGET_NAMES = ("MIN_RUN_SECONDS", "DEFAULT_CAP_24H", "DEFAULT_CAP_7D")
# The regex the engine used before the file existed, written out in full: the built-in list plus the x-rapidapi key.
PINNED_CREDENTIAL = (r"sk-ant-[\w-]{10,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w{20,}|AKIA[0-9A-Z]{12,}|"
                     r"-----BEGIN [A-Z ]*PRIVATE KEY-----|x-rapidapi-key\s*[:=]\s*\w{16,}")
EVENT = {"action": "opened", "issue": {"number": 7, "title": "Add a thing", "state": "open", "labels": [],
                                       "author_association": "OWNER", "user": {"login": "o"}}}


@pytest.fixture
def cfg():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


@pytest.fixture
def engine(monkeypatch):
    """The engine's values, restored after the test: a test that applies another file leaves no trace."""
    for name in ENGINE_NAMES:
        monkeypatch.setattr(sdlc, name, getattr(sdlc, name))
    for name in BUDGET_NAMES:
        monkeypatch.setattr(budget, name, getattr(budget, name))
    return sdlc


def write(tmp_path, data, name="sdlc-config.json"):
    path = tmp_path / name
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def decide_with(folder, *args):
    """The decision the CLI writes for the fixture issue, run with the given options before the command name."""
    folder.mkdir(parents=True, exist_ok=True)
    event, out = folder / "event.json", folder / "decision.json"
    event.write_text(json.dumps(EVENT), encoding="utf-8")
    sdlc.main([*args, "decide", "--event", str(event), "--out", str(out)])
    return json.loads(out.read_text(encoding="utf-8"))


def run_steps():
    """Every `run:` script of the stage job, in order, with its step name."""
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["stage"]["steps"]
    return [(s.get("name", ""), s["run"]) for s in steps if "run" in s]


def covers(entry, path):
    entry = entry.rstrip("/")
    return path == entry or path.startswith(entry + "/")


# ------------------------------------------------------- (a) the file holds the built-in values
def test_the_file_holds_exactly_the_built_in_engine_values(cfg):
    assert cfg["agent_branch_prefix"] == sdlc.AGENT_BRANCH_PREFIX
    assert cfg["artifact_dir"] == sdlc.WORK
    assert set(cfg["trusted_associations"]) == sdlc.TRUSTED and len(cfg["trusted_associations"]) == 3
    assert cfg["label_to_stage"] == sdlc.LABEL_TO_STAGE
    assert set(cfg["requestable_labels"]) == sdlc.REQUESTABLE_LABELS and len(cfg["requestable_labels"]) == len(
        sdlc.REQUESTABLE_LABELS)
    assert cfg["stages"] == sdlc.STAGES
    assert cfg["protected_paths"] == sdlc.PROTECTED
    assert cfg["limits"] == {"max_files": sdlc.MAX_FILES, "max_added_bytes": sdlc.MAX_ADDED_BYTES}
    assert cfg["secret_patterns_extra"] == sdlc.SECRET_PATTERNS_EXTRA
    assert cfg["budget"] == {"cap_24h": budget.DEFAULT_CAP_24H, "cap_7d": budget.DEFAULT_CAP_7D,
                             "min_run_seconds": budget.MIN_RUN_SECONDS}


def test_the_credential_regex_built_from_the_file_is_the_pinned_one(cfg):
    assert "|".join([sdlc._CREDENTIAL_BASE, *cfg["secret_patterns_extra"]]) == PINNED_CREDENTIAL
    assert sdlc._CREDENTIAL.pattern == PINNED_CREDENTIAL


def test_every_stage_output_under_the_artifact_dir_starts_with_it(cfg):
    for name, stage in cfg["stages"].items():
        for path in stage["writes"]:
            if "{n}" in path:
                assert path.startswith(cfg["artifact_dir"] + "/"), (name, path)


def test_the_values_the_yaml_holds_match_the_file(cfg):
    """YAML cannot read JSON, so these values stay in the workflow text. A typo in the file, or a drift, fails here."""
    sdlc_yml, tests_yml = WORKFLOW.read_text(), TESTS_WORKFLOW.read_text()
    branch = cfg["default_branch"]
    assert f"origin/{branch}...HEAD" in sdlc_yml and f"--base {branch} " in sdlc_yml
    assert f"--model {cfg['model']}" in sdlc_yml
    assert f"runs-on: {cfg['runner']}" in sdlc_yml and f"runs-on: {cfg['runner']}" in tests_yml
    assert f'-m "{cfg["commit_title"]}"' in sdlc_yml and f'--title "{cfg["pr_title"]}"' in sdlc_yml
    identity = cfg["git_identity"]
    assert f'user.name "{identity["name"]}"' in sdlc_yml and f'user.email "{identity["email"]}"' in sdlc_yml
    test = cfg["test"]
    assert f'python-version: "{test["python"]}"' in tests_yml
    assert f"- run: {test['command']}" in tests_yml
    assert re.search(rf"^  {re.escape(test['check_name'])}:$", tests_yml, re.M)
    assert (ROOT / ".github" / "workflows" / test["workflow"]).is_file()


# ------------------------------------------------------- (b) no --config gives the built-in values; a missing path fails
def test_no_config_argument_loads_as_none_and_the_built_in_values_stay(engine, tmp_path):
    before = {name: getattr(engine, name) for name in ENGINE_NAMES}
    assert config.load(None) is None
    engine.configure(config.load(None))
    assert {name: getattr(engine, name) for name in ENGINE_NAMES} == before


def test_a_config_path_naming_no_file_raises_and_never_falls_back(tmp_path):
    with pytest.raises(ConfigError):
        config.load(tmp_path / "missing.json")


def test_a_missing_config_file_exits_non_zero_and_writes_no_output(tmp_path):
    out = tmp_path / "decision.json"
    event = tmp_path / "event.json"
    event.write_text(json.dumps(EVENT), encoding="utf-8")
    run = subprocess.run([sys.executable, "-m", "sdlc_engine", "--config", str(tmp_path / "missing.json"), "decide",
                          "--event", str(event), "--out", str(out)],
                         cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, capture_output=True, text=True)
    assert run.returncode != 0
    assert "config file is missing" in run.stderr
    assert not out.exists()


def test_the_cli_with_no_config_argument_decides_with_the_built_in_values(engine, tmp_path):
    bare = decide_with(tmp_path / "bare")
    assert bare["stage"] == "intent" and bare["branch"] == "agent/7-add-a-thing"


def test_no_config_argument_keeps_the_built_in_budget_caps(engine):
    budget.configure(config.load(None))
    assert (budget.MIN_RUN_SECONDS, budget.DEFAULT_CAP_24H, budget.DEFAULT_CAP_7D) == (30, 60, 240)


# ------------------------------------------------------- (c) a malformed file raises and never falls back
@pytest.mark.parametrize("text", ["{not json", "[]", '"a string"', "null", ""])
def test_a_file_that_is_not_a_json_object_raises(tmp_path, text):
    with pytest.raises(ConfigError):
        config.load(write(tmp_path, text))


MALFORMED = {
    "a required key is missing": lambda d: d.pop("protected_paths"),
    "a key is misspelled": lambda d: d.__setitem__("protectd_paths", d.pop("protected_paths")),
    "turns is text": lambda d: d["stages"]["intent"].__setitem__("turns", "12"),
    "a stage lacks tools": lambda d: d["stages"]["spec"].pop("tools"),
    "a stage has an unknown key": lambda d: d["stages"]["spec"].__setitem__("skippable", True),
    "a stage is not an object": lambda d: d["stages"].__setitem__("intent", ["x"]),
    "stages is empty": lambda d: d.__setitem__("stages", {}),
    "a label maps to no stage": lambda d: d["label_to_stage"].__setitem__("agent:intent", "nope"),
    "a limit is negative": lambda d: d.__setitem__("limits", {"max_files": -1, "max_added_bytes": 400000}),
    "a limit is a boolean": lambda d: d.__setitem__("limits", {"max_files": True, "max_added_bytes": 400000}),
    "artifact_dir uses an unknown placeholder": lambda d: d.__setitem__("artifact_dir", "docs/{x}"),
    "a secret pattern does not compile": lambda d: d.__setitem__("secret_patterns_extra", ["(unclosed"]),
    "trusted_associations is text": lambda d: d.__setitem__("trusted_associations", "OWNER"),
    "the branch prefix is empty": lambda d: d.__setitem__("agent_branch_prefix", ""),
    "a budget section has an unknown key": lambda d: d["budget"].__setitem__("cap_1d", 5),
    "a test value is empty": lambda d: d["test"].__setitem__("command", ""),
}


@pytest.mark.parametrize("change", MALFORMED.values(), ids=MALFORMED.keys())
def test_a_file_with_a_bad_value_raises(cfg, tmp_path, change):
    change(cfg)
    with pytest.raises(ConfigError):
        config.load(write(tmp_path, cfg))


def test_the_engine_stops_on_a_malformed_file_and_writes_no_decision(engine, tmp_path, cfg):
    cfg["limits"]["max_files"] = "60"
    bad = write(tmp_path, cfg)
    with pytest.raises(ConfigError):
        decide_with(tmp_path / "run", "--config", str(bad))
    assert not (tmp_path / "run" / "decision.json").exists()
    with pytest.raises(ConfigError):
        budget.main(["--config", str(bad), "--run-id", "1"])        # raised before any call to gh


def test_the_engine_uses_the_values_in_the_file_it_is_given(engine, tmp_path, cfg):
    cfg["agent_branch_prefix"] = "bot/"
    decision = decide_with(tmp_path / "run", "--config", str(write(tmp_path, cfg)))
    assert decision["branch"] == "bot/7-add-a-thing"
    assert engine.AGENT_BRANCH_PREFIX == "bot/"


# ------------------------------------------------------- (d) every trusted checkout fetches the file
def trusted_checkouts():
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["stage"]["steps"]
    return [s for s in steps if s.get("name", "").startswith(LOAD) and "uses" in s]


def test_every_trusted_checkout_fetches_the_config_file_and_the_src():
    checkouts = trusted_checkouts()
    assert len(checkouts) == 3
    for s in checkouts:
        entries = [line.strip() for line in s["with"]["sparse-checkout"].splitlines() if line.strip()]
        assert "src" in entries, s["name"]
        assert any(covers(entry, ".github/sdlc-config.json") for entry in entries), s["name"]
        assert s["with"]["path"] == "trusted" and s["with"]["ref"] == "${{ github.sha }}", s["name"]


def test_every_engine_call_passes_the_config_it_reads():
    """Before the trusted copy exists, decide and budget read the trigger commit's file; after it, the trusted copy's."""
    calls = [(name, line) for name, script in run_steps() for line in script.splitlines() if "-m sdlc_engine" in line]
    assert calls
    for name, line in calls:
        if "$TRUSTED_SRC" in line:
            assert TRUSTED_CONFIG in line, (name, line)
        else:
            assert WORKSPACE_CONFIG in line and "PYTHONPATH=src" in line, (name, line)


def test_the_file_the_first_steps_read_is_in_the_repository_root_config_dir():
    assert CONFIG.is_file() and config.load(CONFIG) is not None
