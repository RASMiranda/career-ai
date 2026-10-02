import json
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from jobscan.apply import cli, faillog, policy, summary
from jobscan.apply.adapters import ApplyFailure, Code, detect_ats, resolve_value
from jobscan.apply.queue import Queue
from jobscan.blacklist import Blacklist

BL = Blacklist(["Proxify"])
AUTH_ON = {"application_submission": {"allow_auto_submit": True, "acknowledged_on": "2026-10-15"}}
AUTH_OFF = {"application_submission": {"allow_auto_submit": False, "acknowledged_on": ""}}


def item(**o):
    base = {"title": "Java Lead", "company": "Acme", "fit": 90, "tier": "core",
            "confidence": "high", "url": "https://jobs.lever.co/acme/123"}
    return {**base, **o}


def cfg(mode="auto", **auto):
    return policy.apply_cfg({"apply": {"mode": mode, "auto": auto}})


# ------------------------------------------------------------------- detection
@pytest.mark.parametrize("url,ats", [
    ("https://boards.greenhouse.io/acme/jobs/1", "greenhouse"),
    ("https://job-boards.greenhouse.io/acme/jobs/1", "greenhouse"),
    ("https://jobs.lever.co/acme/1", "lever"),
    ("https://jobs.ashbyhq.com/acme/1", "ashby"),
    ("https://www.linkedin.com/jobs/view/1", None),
    ("https://evil.test/jobs.lever.co/x", None),
    ("not a url", None),
])
def test_detect_ats(url, ats):
    assert detect_ats(url) == ats


# ---------------------------------------------------------------------- answers
def test_answers_never_guess():
    app = {"first_name": "Ana", "last_name": "Silva", "email": "a@b.test", "phone": ""}
    assert resolve_value("First name *", app, {}) == "Ana"
    assert resolve_value("Full name", app, {}) == "Ana Silva"
    assert resolve_value("Phone", app, {}) is None                       # empty = unknown
    assert resolve_value("Salary expectations", app, {}) is None         # no built-in
    assert resolve_value("Salary expectations", app, {"salary expectation": ""}) is None
    assert resolve_value("Salary expectations", app, {"salary expectation": "Negotiable"}) == "Negotiable"
    assert resolve_value("Email", app, {"email": "other@b.test"}) == "other@b.test"  # explicit wins


# ----------------------------------------------------------------------- policy
def test_manual_mode_never_auto_approves(tmp_path):
    assert policy.initial_status(item(), cfg("manual"), AUTH_ON, Queue(tmp_path), BL)[0] == "queued"


def test_auto_approves_only_when_everything_passes(tmp_path):
    q = Queue(tmp_path)
    assert policy.initial_status(item(), cfg(), AUTH_ON, q, BL)[0] == "approved"


@pytest.mark.parametrize("override,why", [
    ({"fit": 70}, "fit"),
    ({"confidence": "medium"}, "confidence"),
    ({"tier": "radar"}, "tier"),
    ({"url": "https://www.linkedin.com/jobs/view/1"}, "adapter"),
])
def test_auto_holds_back_weak_matches(tmp_path, override, why):
    status, notes = policy.initial_status(item(**override), cfg(), AUTH_ON, Queue(tmp_path), BL)
    assert status == "queued" and any(why in n for n in notes)


def test_master_switch_must_be_on_and_dated(tmp_path):
    status, notes = policy.initial_status(item(), cfg(), AUTH_OFF, Queue(tmp_path), BL)
    assert status == "queued" and any("master switch" in n for n in notes)
    half = {"application_submission": {"allow_auto_submit": True, "acknowledged_on": ""}}
    assert policy.initial_status(item(), cfg(), half, Queue(tmp_path), BL)[0] == "queued"


def test_blacklist_wins_over_everything(tmp_path):
    status, notes = policy.initial_status(item(company="Proxify AB"), cfg(), AUTH_ON, Queue(tmp_path), BL)
    assert status == "skipped" and "blacklisted" in notes[0]


def test_one_application_per_company_window(tmp_path):
    q = Queue(tmp_path)
    q.add("old", item(status="submitted"))
    q.set("old", "submitted")
    status, notes = policy.initial_status(item(), cfg(), AUTH_ON, q, BL)
    assert status == "queued" and any("recently" in n for n in notes)


def test_caps_count_recent_submissions(tmp_path):
    q = Queue(tmp_path)
    c = cfg(max_per_day=2, max_per_week=3)
    assert policy.remaining_quota(c, q) == 2
    for i in range(2):
        q.add(f"k{i}", item(company=f"Co{i}", status="queued")); q.set(f"k{i}", "submitted")
    assert policy.remaining_quota(c, q) == 0
    q.items["k0"]["submitted_at"] = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    assert policy.remaining_quota(c, q) == 1       # day cap freed, week cap not


# ---------------------------------------------------------------------- queue
def test_queue_prefix_resolution_and_persistence(tmp_path):
    q = Queue(tmp_path)
    q.add("abcdef123456", item(status="queued")); q.add("abcxyz999999", item(status="queued"))
    q.save()
    q2 = Queue(tmp_path)
    assert q2.resolve("abcd") == "abcdef123456"
    with pytest.raises(KeyError):
        q2.resolve("abc")        # ambiguous
    with pytest.raises(KeyError):
        q2.resolve("zzz")


# --------------------------------------------------------------------- faillog
def test_failure_log_redacts_personal_data(tmp_path):
    log = faillog.FailureLog(tmp_path, secrets=["Ana", "Silva"])
    path = log.write({"candidate_key": "k", "error_code": "VALIDATION_ERROR",
                      "message": "Ana Silva rejected: ana.silva@mail.test +351 912 345 678",
                      "details": {"visible_errors": ["Invalid phone +66 81 234 5678", "ana@x.test"]}})
    text = path.read_text()
    for leaked in ("Ana", "Silva", "ana.silva@mail.test", "912 345 678", "81 234 5678", "ana@x.test"):
        assert leaked not in text
    assert "[email]" in text and "[phone]" in text


def test_bundle_strips_company_title_and_path(tmp_path):
    entry = {"at": datetime.now(timezone.utc).isoformat(), "company": "SecretCorp",
             "title": "Head of Stuff", "url": "https://boards.greenhouse.io/secretcorp/jobs/99",
             "ats": "greenhouse", "adapter": "greenhouse", "mode": "auto", "step": "fill",
             "error_code": "UNKNOWN_REQUIRED_FIELD", "message": "1 required field",
             "details": {"unknown_fields": ["Salary expectations"]}}
    text = faillog.bundle([entry, entry])
    assert "SecretCorp" not in text and "Head of Stuff" not in text and "/secretcorp/" not in text
    assert "boards.greenhouse.io" in text and "Salary expectations" in text and "x2" in text


# ------------------------------------------------------------------------ CLI
def make_data(tmp_path, mode="manual", switch=False):
    (tmp_path / "profiles/p/01-knowledge").mkdir(parents=True)
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({
        "blacklist": {"companies": ["Proxify"]},
        "apply": {"mode": mode},
        "profiles": [{"id": "p", "criteria": "x", "cv": {"dir": "cv-files"}}]}))
    (tmp_path / "cv-files").mkdir()
    (tmp_path / "cv-files" / "general.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "authorization.yaml").write_text(yaml.safe_dump({
        "active": True,
        "application_submission": {"allow_auto_submit": switch,
                                   "acknowledged_on": "2026-10-15" if switch else ""}}))
    (tmp_path / "applicant.yaml").write_text(yaml.safe_dump({
        "applicant": {"first_name": "Ana", "last_name": "Silva", "email": "a@b.test"}}))
    cands = {"candidates": [
        {"candidate_key": "aaaa1111bbbb2222", "profile": "p", "source": "s", "title": "Java",
         "company": "Acme", "url": "https://jobs.lever.co/acme/1"},
        {"candidate_key": "cccc3333dddd4444", "profile": "p", "source": "s", "title": "Java",
         "company": "Proxify", "url": "https://x.test/2"}]}
    decs = [{"candidate_key": k, "fit": 90, "tier": "core", "confidence": "high",
             "disposition": "email", "why": "w", "cv": "general"} for k in ("aaaa1111bbbb2222", "cccc3333dddd4444")]
    (tmp_path / "c.json").write_text(json.dumps(cands))
    (tmp_path / "d.json").write_text(json.dumps(decs))
    return ["--data", str(tmp_path)]


def run_cli(base, *args):
    return cli.main([*base, *args])


def test_cli_manual_flow(tmp_path, capsys):
    base = make_data(tmp_path)
    assert run_cli(base, "enqueue", "--candidates", str(tmp_path / "c.json"),
                   "--decisions", str(tmp_path / "d.json")) == 0
    q = Queue(tmp_path)
    assert q.items["aaaa1111bbbb2222"]["status"] == "queued"
    assert q.items["aaaa1111bbbb2222"]["cv"] == "general"
    assert q.items["cccc3333dddd4444"]["status"] == "skipped"         # blacklisted
    assert run_cli(base, "approve", "aaaa11") == 0
    assert Queue(tmp_path).items["aaaa1111bbbb2222"]["approval"] == "user"
    assert run_cli(base, "run") == 0                                  # manual mode: nothing runs
    assert "nothing to run" in capsys.readouterr().out
    assert run_cli(base, "done", "aaaa11") == 0
    assert Queue(tmp_path).items["aaaa1111bbbb2222"]["status"] == "done"


def test_cli_enqueue_is_idempotent(tmp_path):
    base = make_data(tmp_path)
    args = ["enqueue", "--candidates", str(tmp_path / "c.json"), "--decisions", str(tmp_path / "d.json")]
    run_cli(base, *args); run_cli(base, *args)
    assert len(Queue(tmp_path).items) == 2


def test_cli_off_mode_queues_nothing(tmp_path):
    base = make_data(tmp_path, mode="off")
    run_cli(base, "enqueue", "--candidates", str(tmp_path / "c.json"), "--decisions", str(tmp_path / "d.json"))
    assert Queue(tmp_path).items == {}


def test_auto_run_refuses_without_master_switch(tmp_path, capsys):
    base = make_data(tmp_path, mode="auto", switch=False)
    assert run_cli(base, "run") == 2
    assert "Refusing" in capsys.readouterr().err


def test_auto_run_records_failure_and_hands_to_human(tmp_path, monkeypatch, capsys):
    base = make_data(tmp_path, mode="auto", switch=True)
    run_cli(base, "enqueue", "--candidates", str(tmp_path / "c.json"), "--decisions", str(tmp_path / "d.json"))
    assert Queue(tmp_path).items["aaaa1111bbbb2222"]["status"] == "approved"   # passed auto policy

    class Boom:
        def apply(self, *a, **k):
            raise ApplyFailure(Code.UNKNOWN_REQUIRED_FIELD, "1 required field", "fill",
                               {"unknown_fields": ["Salary expectations"]})
    monkeypatch.setattr(cli, "pick_adapter", lambda url, allowed=None: Boom())
    assert run_cli(base, "run") == 0
    item_ = Queue(tmp_path).items["aaaa1111bbbb2222"]
    assert item_["status"] == "failed" and item_["error_code"] == "UNKNOWN_REQUIRED_FIELD"

    md = summary.render_markdown(Queue(tmp_path))
    assert "Apply manually" in md and "https://jobs.lever.co/acme/1" in md
    assert "required questions" in md                      # plain-language reason
    logged = list((tmp_path / "logs/apply").glob("*.jsonl"))
    assert logged and "UNKNOWN_REQUIRED_FIELD" in logged[0].read_text()

    assert run_cli(base, "bundle", "--out", str(tmp_path / "f.md")) == 0
    assert "Salary expectations" in (tmp_path / "f.md").read_text()


def test_auto_run_success_and_cap(tmp_path, monkeypatch):
    base = make_data(tmp_path, mode="auto", switch=True)
    run_cli(base, "enqueue", "--candidates", str(tmp_path / "c.json"), "--decisions", str(tmp_path / "d.json"))

    class Ok:
        def apply(self, *a, **k):
            from jobscan.apply.adapters import ApplyResult
            return ApplyResult("submitted", ["First name"], "thank you")
    monkeypatch.setattr(cli, "pick_adapter", lambda url, allowed=None: Ok())
    assert run_cli(base, "run") == 0
    assert Queue(tmp_path).items["aaaa1111bbbb2222"]["status"] == "submitted"


def test_dry_run_failure_is_logged_but_status_unchanged(tmp_path, monkeypatch):
    base = make_data(tmp_path, mode="auto", switch=True)
    run_cli(base, "enqueue", "--candidates", str(tmp_path / "c.json"), "--decisions", str(tmp_path / "d.json"))

    class Boom:
        def apply(self, *a, **k):
            raise ApplyFailure(Code.FORM_CHANGED, "no form", "reach_form")
    monkeypatch.setattr(cli, "pick_adapter", lambda url, allowed=None: Boom())
    assert run_cli(base, "run", "--dry-run") == 0
    assert Queue(tmp_path).items["aaaa1111bbbb2222"]["status"] == "approved"
    assert list((tmp_path / "logs/apply").glob("*.jsonl"))


def test_missing_cv_is_a_clean_failure(tmp_path):
    cfg = {"profiles": [{"id": "p", "cv": {"default": "g", "files": {"g": "/nope/cv.pdf"}}}]}
    with pytest.raises(ApplyFailure) as e:
        cli._cv_for({"profile": "p"}, tmp_path, cfg)
    assert e.value.code == Code.CV_MISSING


def test_chosen_cv_wins_over_default(tmp_path):
    for name in ("Ana Silva Resume General", "Ana Silva Resume Tech Lead"):
        (tmp_path / "CV" / name).mkdir(parents=True)
        (tmp_path / "CV" / name / f"{name}.pdf").write_bytes(b"%PDF")
    cfg = {"profiles": [{"id": "p", "display_name": "Ana",
                         "cv": {"dir": "CV", "default": "general"}}]}
    assert cli._cv_for({"profile": "p", "cv": "tech-lead"}, tmp_path, cfg).endswith("Tech Lead.pdf")
    assert cli._cv_for({"profile": "p"}, tmp_path, cfg).endswith("General.pdf")
    assert cli._cv_for({"profile": "other"}, tmp_path, cfg) is None


def test_blacklist_cli(tmp_path, capsys):
    base = make_data(tmp_path)
    run_cli(base, "blacklist", "test", "PROXIFY ab")
    assert "BLOCKED by Proxify" in capsys.readouterr().out
    run_cli(base, "blacklist", "test", "Acme")
    assert "not blacklisted" in capsys.readouterr().out
