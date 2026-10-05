import json
import subprocess

import pytest
import yaml

from jobscan import pipeline
from jobscan.apply.queue import Queue

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
    for d in ("reports", "state", "applications", "logs"):
        (data / d).mkdir(); (data / d / ".gitkeep").write_text("")
    (data / "config.yaml").write_text(yaml.safe_dump({"profiles": [{
        "id": "p", "notify": {"email": ["a@mail.test"]},
        "prefilter": {"reject_title": [r"\bjunior\b"]}}]}))
    (data / "authorization.yaml").write_text(yaml.safe_dump({"active": True}))
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
    assert "k1" in json.loads((data / "state/job-scan-seen.json").read_text())


def test_prepare_prints_a_brief_for_the_model_and_defers_over_the_cap(tmp_path, monkeypatch, capsys):
    data, work = make_repo(tmp_path), tmp_path / "work"
    cfg = yaml.safe_load((data / "config.yaml").read_text())
    cfg["profiles"][0]["prefilter"]["max_to_score"] = 1
    (data / "config.yaml").write_text(yaml.safe_dump(cfg))
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
    (data / "authorization.yaml").write_text(yaml.safe_dump({"active": False}))
    monkeypatch.setattr(pipeline.collect, "main", lambda argv: pytest.fail("collected"))
    assert pipeline.main(["prepare", "--data", str(data), "--work", str(tmp_path / "w")]) == 2


def test_publish_falls_back_when_main_is_rejected(tmp_path):
    data = make_repo(tmp_path, reject_main=True)
    (data / "reports/r.md").write_text("report")
    assert pipeline.publish(data, "job-scan test").startswith("claude/job-scan")
    assert "job-scan test" in git(tmp_path / "origin.git", "log", "-1", "--format=%s", "claude/job-scan")


def test_publish_with_nothing_changed_does_nothing(tmp_path):
    assert pipeline.publish(make_repo(tmp_path), "x") == "nothing to commit"
