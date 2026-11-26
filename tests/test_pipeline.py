import json
import shutil
import subprocess

import pytest
import yaml

from jobscan import pipeline
from jobscan.apply.queue import Queue
from profile_helpers import ensure_profile, write_apply_config, write_profile

LONG = "We build services all day long. " * 20


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True).stdout


def make_repo(tmp_path, reject_main=False):
    """A data repo (clone) with an origin that can be told to refuse main."""
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    if reject_main:
        hook = remote / "hooks" / "pre-receive"
        hook.write_text('#!/bin/sh\nwhile read o n ref; do [ "$ref" = refs/heads/main ] && exit 1; done\nexit 0\n')
        hook.chmod(0o755)
    data = tmp_path / "data"
    subprocess.run(["git", "clone", "-q", str(remote), str(data)], check=True, capture_output=True)
    git(data, "config", "user.email", "t@t.test"); git(data, "config", "user.name", "t")
    git(data, "checkout", "-q", "-b", "main")
    (data / "profiles/p/01-knowledge").mkdir(parents=True)
    (data / "profiles/p/01-knowledge/05-job-match.md").write_text("x")
    (data / "config.yaml").write_text(yaml.safe_dump({}))
    write_profile(data, "p", {"notify": {"email": ["a@mail.test"]},
                              "prefilter": {"reject_title": [r"\bjunior\b"]}})
    (data / "profiles/p").mkdir(parents=True, exist_ok=True)
    (data / "profiles/p/authorization.yaml").write_text(yaml.safe_dump({"active": True}))
    git(data, "add", "-A"); git(data, "commit", "-qm", "init")
    if not reject_main:
        git(data, "push", "-q", "origin", "main")
    return data


def cand(key, title, **kw):
    return {"candidate_key": key, "profile": "p", "source": "s", "title": title, "company": "Acme",
            "url": "https://x.test/" + key, "description": LONG, "location": "", "contract_type": "",
            "salary": "", **kw}


def write_candidates(work, cands):
    work.mkdir(exist_ok=True)
    (work / "candidates.json").write_text(json.dumps({"generated_on": "2026-10-05", "errors": [],
        "counts": {"new": len(cands), "already_seen": 0, "blacklisted": 0}, "candidates": cands}))


def test_finish_merges_auto_and_model_decisions_and_asks_for_the_email(tmp_path, capsys):
    ensure_profile(tmp_path)
    data, work = make_repo(tmp_path), tmp_path / "work"
    cands = [cand("k1", "Senior Java Engineer"), cand("k2", "Junior Developer")]
    write_candidates(work, cands)
    (work / "auto-decisions.json").write_text(json.dumps([
        {"candidate_key": "k2", "fit": 0, "tier": "radar", "confidence": "high",
         "disposition": "discarded", "why": "prefilter: junior"}]))
    (work / "decisions.json").write_text(json.dumps([
        {"candidate_key": "k1", "fit": 90, "tier": "core", "confidence": "high",
         "disposition": "email", "why": "match", "cv": ""}]))
    assert pipeline.main(["finish", "--data", str(data), "--work", str(work)]) == 0
    out = capsys.readouterr().out
    assert "SEND these emails" in out and "a@mail.test" in out and "[Job Scan] 2026-10-05" in out
    assert "email: 1" in out and "scored by the model: 1" in out
    assert (work / "out/email-p.html").is_file()
    assert git(data, "log", "--oneline").count("\n") == 1          # nothing committed before the email


def test_finish_stops_on_invalid_decisions_and_changes_nothing(tmp_path, capsys):
    data, work = make_repo(tmp_path), tmp_path / "work"
    write_candidates(work, [cand("k1", "Senior Java Engineer")])
    (work / "decisions.json").write_text("[]")                     # k1 never decided
    assert pipeline.main(["finish", "--data", str(data), "--work", str(work)]) == 1
    assert "STOP: validation failed" in capsys.readouterr().err
    assert not (data / "applications/queue.json").exists()


def test_model_decision_overrides_the_automatic_one(tmp_path):
    ensure_profile(tmp_path)
    data, work = make_repo(tmp_path), tmp_path / "work"
    write_candidates(work, [cand("k2", "Junior Developer")])
    (work / "auto-decisions.json").write_text(json.dumps([
        {"candidate_key": "k2", "fit": 0, "tier": "radar", "confidence": "high",
         "disposition": "discarded", "why": "prefilter: junior"}]))
    (work / "decisions.json").write_text(json.dumps([
        {"candidate_key": "k2", "fit": 50, "tier": "radar", "confidence": "low",
         "disposition": "discarded", "why": "model looked again"}]))
    assert pipeline.main(["finish", "--data", str(data), "--work", str(work)]) == 0
    merged = json.loads((work / "all-decisions.json").read_text())
    assert [d["why"] for d in merged] == ["model looked again"]


def test_nothing_to_score_runs_to_the_end_with_one_command(tmp_path, monkeypatch, capsys):
    ensure_profile(tmp_path)
    data, work = make_repo(tmp_path), tmp_path / "work"
    def fake_collect(argv):
        write_candidates(work, [cand("k1", "Junior Developer")])
        return 0
    monkeypatch.setattr(pipeline.collect, "main", fake_collect)
    assert pipeline.main(["prepare", "--data", str(data), "--work", str(work)]) == 0
    out = capsys.readouterr().out
    assert "NOTHING TO SCORE" in out and "No email to send" in out and "state saved: main" in out
    assert "auto-discarded by prefilter" in out
    assert "job-scan 2026-10-05" in git(data, "log", "-1", "--format=%s")
    assert "job-scan 2026-10-05" in git(tmp_path / "origin.git", "log", "-1", "--format=%s", "main")
    assert "k1" in json.loads((data / "profiles/p/state/job-scan-seen.json").read_text())


def test_nothing_to_score_still_lists_the_email_when_applications_wait(tmp_path, monkeypatch, capsys):
    ensure_profile(tmp_path)
    data, work = make_repo(tmp_path), tmp_path / "work"
    monkeypatch.setattr(pipeline.collect, "main", lambda argv: write_candidates(
        work, [cand("k1", "Junior Developer")]) or 0)
    monkeypatch.setattr(pipeline.report, "render_applications", lambda *a, **k: "<p>waiting</p>")
    assert pipeline.main(["prepare", "--data", str(data), "--work", str(work)]) == 0
    out = capsys.readouterr().out
    assert "NOTHING TO SCORE" in out and "the email is still due" in out
    assert "SEND these emails" in out and "a@mail.test" in out
    assert "state saved" not in out                                # committed only after the send


def test_prepare_prints_a_brief_for_the_model_and_defers_over_the_cap(tmp_path, monkeypatch, capsys):
    data, work = make_repo(tmp_path), tmp_path / "work"
    prof = yaml.safe_load((data / "profiles/p/profile.yaml").read_text())
    prof["prefilter"]["max_to_score"] = 1
    (data / "profiles/p/profile.yaml").write_text(yaml.safe_dump(prof))
    monkeypatch.setattr(pipeline.collect, "main", lambda argv: write_candidates(
        work, [cand("k1", "Senior Java Engineer"), cand("k2", "Tech Lead Java"), cand("k3", "Junior Dev")]) or 0)
    assert pipeline.main(["prepare", "--data", str(data), "--work", str(work)]) == 0
    out = capsys.readouterr().out
    assert "1 auto-discarded" in out and "1 need scoring" in out and "1 deferred" in out
    assert "## k1 | Senior Java Engineer" in out and "k2" not in out
    kept = [c["candidate_key"] for c in json.loads((work / "candidates.json").read_text())["candidates"]]
    assert kept == ["k1", "k3"]                  # the deferred one is not marked seen later


def test_inactive_authorization_stops_before_collecting(tmp_path, monkeypatch, capsys):
    data = make_repo(tmp_path)
    (data / "profiles/p/authorization.yaml").write_text(yaml.safe_dump({"active": False}))
    monkeypatch.setattr(pipeline.collect, "main", lambda argv: pytest.fail("collected"))
    assert pipeline.main(["prepare", "--data", str(data), "--work", str(tmp_path / "w")]) == 2


def test_publish_falls_back_when_main_is_rejected(tmp_path):
    ensure_profile(tmp_path)
    data = make_repo(tmp_path, reject_main=True)
    (data / "profiles/p/reports").mkdir(parents=True)
    (data / "profiles/p/reports/r.md").write_text("report")
    assert pipeline.publish(data, "job-scan test").startswith("claude/job-scan")
    assert "job-scan test" in git(tmp_path / "origin.git", "log", "-1", "--format=%s", "claude/job-scan")


def test_publish_with_nothing_changed_does_nothing(tmp_path):
    assert pipeline.publish(make_repo(tmp_path), "x") == "nothing to commit"


def with_profiles(data, *ids):
    """Give each id a profile folder (profile.yaml marks it) holding files the routine must never publish."""
    for pid in ids:
        base = data / "profiles" / pid
        for rel in ("profile.yaml", "answer_bank.yaml", "authorization.yaml", "apply/triage.yaml",
                    "applications/answers.json", "logs/runs.jsonl", "logs/apply/x.jsonl"):
            (base / rel).parent.mkdir(parents=True, exist_ok=True)
            (base / rel).write_text("x")
    git(data, "add", "-A"); git(data, "commit", "-qm", "profiles")


def committed(data) -> list[str]:
    return git(data, "show", "--name-only", "--format=", "HEAD").split()


def test_the_allowlist_never_names_profiles_or_a_profile_folder_as_a_whole(tmp_path):
    data = make_repo(tmp_path)
    with_profiles(data, "p", "q")
    paths = pipeline.publish_paths(data)
    for forbidden in ("profiles", "profiles/p", "profiles/q", "logs", "applications", "applications/answers.json"):
        assert forbidden not in paths
    assert not any(p.endswith(("answer_bank.yaml", "profile.yaml", "authorization.yaml", "answers.json"))
                   for p in paths)
    assert {"profiles/p/reports", "profiles/p/state", "profiles/p/applications/queue.json"} <= set(paths)


def test_a_profile_publish_lands_under_the_profile(tmp_path):
    data = make_repo(tmp_path)
    with_profiles(data, "p")
    for rel in ("reports/d.md", "state/job-scan-seen.json", "applications/queue.json"):
        (data / "profiles/p" / rel).parent.mkdir(parents=True, exist_ok=True)
        (data / "profiles/p" / rel).write_text("{}")
    assert pipeline.publish(data, "scan") == "main"
    assert sorted(committed(data)) == ["profiles/p/applications/queue.json", "profiles/p/reports/d.md",
                                       "profiles/p/state/job-scan-seen.json"]


def test_a_root_form_staged_by_hand_is_refused_and_nothing_is_committed(tmp_path):
    ensure_profile(tmp_path)
    data = make_repo(tmp_path)
    with_profiles(data, "p")
    before = git(data, "rev-parse", "HEAD")
    for rel in ("reports/d.md", "state/job-scan-seen.json", "applications/queue.json"):
        (data / rel).parent.mkdir(parents=True, exist_ok=True)
        (data / rel).write_text("{}")
    git(data, "add", "reports/d.md", "state/job-scan-seen.json", "applications/queue.json")
    with pytest.raises(RuntimeError, match="outside the allowlist"):
        pipeline.publish(data, "scan")
    assert git(data, "rev-parse", "HEAD") == before


def test_other_profile_files_changed_in_the_tree_are_not_committed(tmp_path):
    data = make_repo(tmp_path)
    with_profiles(data, "p")
    (data / "profiles/p/answer_bank.yaml").write_text("changed")          # modified, not staged
    (data / "profiles/p/applications/answers.json").write_text("changed")
    (data / "profiles/p/logs/runs.jsonl").write_text("changed")
    (data / "profiles/p/reports").mkdir()
    (data / "profiles/p/reports/d.md").write_text("r")
    pipeline.publish(data, "scan")
    assert committed(data) == ["profiles/p/reports/d.md"]
    assert "answer_bank.yaml" in git(data, "status", "--short")


def test_two_profiles_each_publish_only_their_own_allowed_files(tmp_path):
    data = make_repo(tmp_path)
    with_profiles(data, "p", "q")
    for pid in ("p", "q"):
        (data / "profiles" / pid / "reports").mkdir()
        (data / "profiles" / pid / "reports/d.md").write_text(pid)
        (data / "profiles" / pid / "profile.yaml").write_text("changed")
    pipeline.publish(data, "scan")
    assert sorted(committed(data)) == ["profiles/p/reports/d.md", "profiles/q/reports/d.md"]


@pytest.mark.parametrize("name", [
    "profiles/p/answer_bank.yaml", "profiles/p/profile.yaml", "profiles/p/authorization.yaml",
    "profiles/p/applications/answers.json", "profiles/p/logs/runs.jsonl", "profiles/p/logs/apply/x.jsonl",
    "profiles/p/apply/triage.yaml", "profiles/p/reportsx/d.md", "profiles/ghost/reports/d.md",
    "authorization.yaml", "config.yaml", "logs/runs.jsonl", "applications/answers.json"])
def test_a_forbidden_path_in_the_index_is_refused_and_nothing_is_committed(tmp_path, name):
    data = make_repo(tmp_path)
    with_profiles(data, "p")
    before = git(data, "rev-parse", "HEAD")
    (data / "profiles/p/reports").mkdir()
    (data / "profiles/p/reports/d.md").write_text("r")
    target = data / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("staged by something else")
    git(data, "add", "-f", name)
    with pytest.raises(RuntimeError, match="allowlist"):
        pipeline.publish(data, "scan")
    assert git(data, "rev-parse", "HEAD") == before
    assert name not in git(data, "diff", "--cached", "--name-only")       # not left staged for a later run


# ---- phase C: --profile on every step ----

def _add_profiles(data, *ids):
    for pid in ids:
        (data / f"profiles/{pid}").mkdir(parents=True, exist_ok=True)
        (data / f"profiles/{pid}/profile.yaml").write_text("display_name: Synthetic\n")
        (data / f"profiles/{pid}/authorization.yaml").write_text("active: true\n")


def _spy_collect(monkeypatch, work, seen):
    def fake(argv):
        seen.append(argv)
        write_candidates(work, [cand("k1", "Junior Developer")])
        return 0
    monkeypatch.setattr(pipeline.collect, "main", fake)


def test_prepare_passes_the_only_profile_to_collect(tmp_path, monkeypatch):
    data, work, seen = make_repo(tmp_path), tmp_path / "work", []
    shutil.rmtree(data / "profiles/p")            # the make_repo profile; this test wants exactly one other
    _add_profiles(data, "x")
    _spy_collect(monkeypatch, work, seen)
    pipeline.main(["prepare", "--data", str(data), "--work", str(work)])
    assert seen[0][-2:] == ["--profile", "x"]


def test_prepare_passes_an_explicit_profile_to_collect(tmp_path, monkeypatch):
    data, work, seen = make_repo(tmp_path), tmp_path / "work", []
    _add_profiles(data, "x", "y")
    _spy_collect(monkeypatch, work, seen)
    pipeline.main(["prepare", "--data", str(data), "--work", str(work), "--profile", "y"])
    assert seen[0][-2:] == ["--profile", "y"]


def test_prepare_without_a_profile_folder_stops_before_writing_anything(tmp_path, monkeypatch, capsys):
    data, work, seen = make_repo(tmp_path), tmp_path / "work", []
    shutil.rmtree(data / "profiles")                 # inline or no profiles: no folder, so no profile files
    _spy_collect(monkeypatch, work, seen)
    assert pipeline.main(["prepare", "--data", str(data), "--work", str(work)]) != 0
    assert not (data / "profiles").exists() and not (data / "state").exists()


@pytest.mark.parametrize("extra", [[], ["--profile", "nobody"]])
def test_several_profiles_without_a_choice_or_an_unknown_one_exit_2(tmp_path, monkeypatch, capsys, extra):
    data = make_repo(tmp_path)
    _add_profiles(data, "x", "y")
    monkeypatch.setattr(pipeline.collect, "main", lambda argv: pytest.fail("collected"))
    for cmd in ("prepare", "finish", "commit"):
        assert pipeline.main([cmd, "--data", str(data), "--work", str(tmp_path / "w"), *extra]) == 2
        assert "config error" in capsys.readouterr().err
