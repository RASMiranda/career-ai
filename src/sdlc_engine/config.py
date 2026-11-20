"""The project values the sdlc engine uses, read from ``.github/sdlc-config.json`` (ADR-060). Stdlib only.

``load`` returns ``None`` when the file is absent: the built-in constants in ``sdlc_engine`` then apply, which is how
the engine behaved before this file existed. A file that is present but malformed raises ``ConfigError``. Nothing
falls back silently: a wrong value could let a stage write where it must not, so the run stops instead.

The file is read from the trigger commit by the workflow's trusted checkouts, so a config change reaches the run only
through a merged PR. Values the GitHub Actions YAML itself holds (runner, model, Python version, titles) are in the
file too; tests/test_sdlc_config_file.py keeps them equal to the workflow text, since YAML cannot read JSON.

The project's own prompt text and owner handle are optional (ADR-065): the ``prompt`` object and ``budget.mention``. A
file without them is valid and the engine uses its generic built-in text, so the engine names no project it was not given.
"""
import json
import re
from pathlib import Path

KEYS = {"default_branch", "agent_branch_prefix", "artifact_dir", "trusted_associations", "label_to_stage",
        "requestable_labels", "stages", "protected_paths", "limits", "secret_patterns_extra", "budget", "model",
        "test", "git_identity", "commit_title", "pr_title", "runner"}
# Optional (ADR-065): the project's own prompt text and budget handle. A file without them is valid and renders the
# generic built-in text, so the engine names no project in a prompt it was not given one for.
OPTIONAL_KEYS = {"prompt"}
PROMPT_KEYS = {"never_touch", "read_first", "support_sources", "support_bundle"}
STAGE_KEYS = {"roles", "needs", "writes", "repo", "tools", "turns"}
OPTIONAL_STAGE_KEYS = {"checkout"}
SECTIONS = {"limits": {"max_files", "max_added_bytes"}, "budget": {"cap_24h", "cap_7d", "min_run_seconds"},
            "test": {"command", "check_name", "workflow", "python"}, "git_identity": {"name", "email"}}
OPTIONAL_SECTION_KEYS = {"budget": {"mention"}}
TEXT_KEYS = ("default_branch", "agent_branch_prefix", "model", "commit_title", "pr_title", "runner")
LIST_KEYS = ("trusted_associations", "requestable_labels", "protected_paths", "secret_patterns_extra")


class ConfigError(ValueError):
    """The config file is present but is not a valid sdlc config."""


def load(path):
    """The parsed config, or None when no path was given at all. Raises ``ConfigError`` when a path is given but names
    no file (fail closed, ADR-060) or when the file is malformed."""
    if path is None:
        return None
    if not Path(path).is_file():
        raise ConfigError(f"{path}: the config file is missing; pass no --config to use the built-in values")
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ConfigError(f"{path}: cannot read it as JSON: {exc}") from None
    problems = problems_in(data)
    if problems:
        raise ConfigError(f"{path}: " + "; ".join(problems))
    return data


def _is_count(value):
    return type(value) is int and value >= 0            # bool is an int in Python; it is never a count here


def _is_text(value):
    return isinstance(value, str) and value != ""


def _is_text_list(value):
    return isinstance(value, list) and all(_is_text(v) for v in value)


def _key_problems(found, wanted, what, optional=()):
    out = []
    if set(wanted) - set(found):
        out.append(f"{what} lacks {', '.join(sorted(set(wanted) - set(found)))}")
    if set(found) - set(wanted) - set(optional):
        out.append(f"{what} has unknown key(s) {', '.join(sorted(set(found) - set(wanted) - set(optional)))}")
    return out


def _prompt_problems(prompt):
    """The optional ``prompt`` object (ADR-065): every key is optional; a key that is present must be the right type."""
    if not isinstance(prompt, dict):
        return ["prompt must be an object"]
    out = _key_problems(prompt, (), "prompt", PROMPT_KEYS)
    for key in ("never_touch", "support_bundle"):
        if key in prompt and not isinstance(prompt[key], str):
            out.append(f"prompt.{key} must be a string (empty leaves the sentence out)")
    if "support_sources" in prompt and not _is_text(prompt["support_sources"]):
        out.append("prompt.support_sources must be a non-empty string")
    if "read_first" in prompt and not (_is_text_list(prompt["read_first"]) and prompt["read_first"]):
        out.append("prompt.read_first must be a non-empty list of non-empty strings")
    return out


def _stage_problems(name, stage):
    if not isinstance(stage, dict):
        return [f"stage {name!r} must be an object"]
    out = []
    if STAGE_KEYS - set(stage):
        out.append(f"stage {name!r} lacks {', '.join(sorted(STAGE_KEYS - set(stage)))}")
    if set(stage) - STAGE_KEYS - OPTIONAL_STAGE_KEYS:
        out.append(f"stage {name!r} has unknown key(s) {', '.join(sorted(set(stage) - STAGE_KEYS - OPTIONAL_STAGE_KEYS))}")
    if out:
        return out
    if not _is_text_list(stage["roles"]):
        out.append(f"stage {name!r}: roles must be a list of names")
    if stage["needs"] is not None and not _is_text(stage["needs"]):
        out.append(f"stage {name!r}: needs must be a file name or null")
    if not _is_text_list(stage["writes"]):
        out.append(f"stage {name!r}: writes must be a list of path patterns")
    if not isinstance(stage["repo"], bool) or not isinstance(stage["tools"], str):
        out.append(f"stage {name!r}: repo must be true or false and tools a string")
    if not _is_count(stage["turns"]) or stage["turns"] < 1:
        out.append(f"stage {name!r}: turns must be a whole number of at least 1")
    if "checkout" in stage and not isinstance(stage["checkout"], bool):
        out.append(f"stage {name!r}: checkout must be true or false")
    return out


def problems_in(data):
    """Every reason ``data`` is not a valid sdlc config, as readable sentences. Empty when it is valid."""
    if not isinstance(data, dict):
        return ["the top level must be a JSON object"]
    out = _key_problems(data, KEYS, "the file", OPTIONAL_KEYS)
    if out:
        return out
    if "prompt" in data:
        out += _prompt_problems(data["prompt"])
    if not isinstance(data["stages"], dict) or not data["stages"]:
        return ["stages must be a non-empty object"]
    for name, stage in data["stages"].items():
        out += _stage_problems(name, stage)
    labels = data["label_to_stage"]
    if not isinstance(labels, dict) or not all(isinstance(v, str) and v in data["stages"] for v in labels.values()):
        out.append("label_to_stage must map each label to a stage that is in stages")
    for key in TEXT_KEYS:
        if not _is_text(data[key]):
            out.append(f"{key} must be a non-empty string")
    if not isinstance(data["artifact_dir"], str):
        out.append("artifact_dir must be a string")
    else:
        try:
            data["artifact_dir"].format(n=1, slug="x")
        except (KeyError, IndexError, ValueError):
            out.append("artifact_dir may use only {n} and {slug}")
    for key in LIST_KEYS:
        if not _is_text_list(data[key]):
            out.append(f"{key} must be a list of non-empty strings")
    for pattern in data["secret_patterns_extra"] if _is_text_list(data["secret_patterns_extra"]) else []:
        try:
            re.compile(pattern)
        except re.error:
            out.append(f"secret_patterns_extra has an invalid regular expression: {pattern!r}")
    for section, wanted in SECTIONS.items():
        value = data[section]
        if not isinstance(value, dict):
            out.append(f"{section} must be an object")
            continue
        out += _key_problems(value, wanted, section, OPTIONAL_SECTION_KEYS.get(section, ()))
        if section in ("limits", "budget") and not all(_is_count(value.get(k)) for k in wanted):
            out.append(f"{section} must hold whole numbers")
        if section in ("test", "git_identity") and not all(_is_text(value.get(k)) for k in wanted):
            out.append(f"{section} must hold non-empty strings")
    budget_section = data["budget"]
    if isinstance(budget_section, dict) and "mention" in budget_section and not isinstance(budget_section["mention"], str):
        out.append("budget.mention must be a string (empty means no handle)")
    return out
