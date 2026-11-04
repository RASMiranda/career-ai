import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from jobscan.apply import cli, faillog, policy, summary
from jobscan.apply.adapters import (
    ApplyFailure,
    ApplyResult,
    Code,
    detect_ats,
    is_confirmation_url,
    resolve_value,
)
from jobscan.apply.queue import Queue
from jobscan.blacklist import Blacklist
from jobscan.config import ConfigError

BL = Blacklist(["Proxify"])
AUTH_ON = {"application_submission": {"master_switch": True, "acknowledged_on": "2026-10-15"}}
AUTH_OFF = {"application_submission": {"master_switch": False, "acknowledged_on": ""}}


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
    ("https://www.linkedin.com/jobs/view/1", "linkedin_easy_apply"),
    ("https://www.linkedin.com/in/someone", None),       # profiles are never a job to apply to
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
    half = {"application_submission": {"master_switch": True, "acknowledged_on": ""}}
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
        "profiles": [{"id": "p", "criteria": "x", "cv": {"dir": "cv-files"},
                      "applicant": {"first_name": "Ana", "last_name": "Silva", "email": "a@b.test"}}]}))
    (tmp_path / "cv-files").mkdir()
    (tmp_path / "cv-files" / "general.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "authorization.yaml").write_text(yaml.safe_dump({
        "active": True,
        "application_submission": {"master_switch": switch,
                                   "acknowledged_on": "2026-10-15" if switch else ""}}))
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
            return ApplyResult("submitted", ["First name"], confirmation_url="https://apply.test/job/1/confirmation")
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


def test_applicant_comes_from_the_profile():
    profile = {"id": "a", "applicant": {"first_name": "Ana", "last_name": "S", "email": "a@b.test"},
               "answers": {"notice period": "1 month"}}
    app, answers = cli._applicant(Path("."), profile)
    assert app["first_name"] == "Ana" and answers == {"notice period": "1 month"}


@pytest.mark.parametrize("applicant", [None, {}, {"first_name": "Ana"}])
def test_incomplete_applicant_is_an_error(applicant):
    with pytest.raises(ConfigError, match="applicant is missing"):
        cli._applicant(Path("."), {"id": "a", "applicant": applicant})


def test_old_applicant_files_are_not_silently_used(tmp_path):
    (tmp_path / "profiles/a").mkdir(parents=True)
    (tmp_path / "profiles/a/applicant.yaml").write_text(yaml.safe_dump({
        "applicant": {"first_name": "Ana", "last_name": "S", "email": "a@b.test"}}))
    with pytest.raises(ConfigError, match="Move the contents of profiles/a/applicant.yaml into it; that file is no longer read"):
        cli._applicant(tmp_path, {"id": "a"})


def test_run_skips_a_profile_without_applicant_but_runs_the_rest(tmp_path, monkeypatch, capsys):
    base = make_data(tmp_path, mode="assisted")
    q = Queue(tmp_path)
    for key, prof in (("aaaa1111bbbb2222", "p"), ("eeee5555ffff6666", "ghost")):
        q.add(key, {"profile": prof, "title": "Java", "company": key[:4], "url": "https://jobs.lever.co/x/1",
                    "fit": 90, "tier": "core", "status": "approved"})
    q.save()
    seen = []
    class Spy:
        def apply(self, job, applicant, *a, **k):
            seen.append(applicant["first_name"])
            raise ApplyFailure(Code.FORM_CHANGED, "no form", "reach_form")
    monkeypatch.setattr(cli, "pick_adapter", lambda url, allowed=None: Spy())
    assert run_cli(base, "run", "--dry-run") == 0
    assert seen == ["Ana"]                                  # only the profile with a file
    assert "SKIPPED profile 'ghost'" in capsys.readouterr().err
    assert Queue(tmp_path).items["eeee5555ffff6666"]["status"] == "approved"   # left for later


def test_run_exits_nonzero_when_no_approved_job_has_an_applicant(tmp_path, monkeypatch):
    base = make_data(tmp_path, mode="assisted")
    q = Queue(tmp_path)
    q.add("eeee5555ffff6666", {"profile": "ghost", "title": "Java", "company": "X",
                               "url": "https://jobs.lever.co/x/1", "fit": 90, "status": "approved"})
    q.save()
    assert run_cli(base, "run", "--dry-run") == 2


def test_consent_pending_is_handed_to_the_human_with_the_link(tmp_path, monkeypatch, capsys):
    base = make_data(tmp_path, mode="auto", switch=True)
    run_cli(base, "enqueue", "--candidates", str(tmp_path / "c.json"), "--decisions", str(tmp_path / "d.json"))

    class Consent:
        def apply(self, *a, **k):
            raise ApplyFailure(Code.CONSENT_PENDING, "1 consent field", "fill",
                               {"consent_fields": ["I agree to the privacy policy"]})
    monkeypatch.setattr(cli, "pick_adapter", lambda url, allowed=None: Consent())
    assert run_cli(base, "run") == 0
    item_ = Queue(tmp_path).items["aaaa1111bbbb2222"]
    assert item_["status"] == "consent_pending" and item_["error_code"] == "consent_pending"
    assert item_["attempts"][-1]["outcome"] == "failed"

    q = Queue(tmp_path)
    assert summary.count_failures(q) == 1                    # the daily email still goes out
    md = summary.render_markdown(q)
    assert "Apply manually" in md and "https://jobs.lever.co/acme/1" in md and "consent" in md.lower()
    logged = [json.loads(line) for p in (tmp_path / "logs/apply").glob("*.jsonl")
              for line in p.read_text(encoding="utf-8").splitlines()]
    assert logged[-1]["error_code"] == "consent_pending"


# ------------------------------------------------------ submission record (P0 item 5)
def test_only_a_confirmation_path_counts_as_confirmed():
    confirmed = ["https://jobs.example.test/acme/jobs/1/confirmation",
                 "https://apply.example.test/confirmation?ref=1", "/confirmation"]
    not_confirmed = ["https://jobs.example.test/acme/jobs/1", "https://apply.example.test/thanks",
                     "https://apply.example.test/confirmation/", "https://apply.example.test/confirmation-old",
                     "https://apply.example.test/submit", ""]
    for url in confirmed:
        assert is_confirmation_url(url), url
    for url in not_confirmed:
        assert not is_confirmation_url(url), url


def test_a_submitted_result_needs_a_confirmation_page_and_is_stamped_in_utc():
    with pytest.raises(ValueError):
        ApplyResult("submitted", [], confirmation_url="https://apply.example.test/thanks")
    res = ApplyResult("submitted", [], confirmation_url="https://apply.example.test/job/1/confirmation")
    assert datetime.fromisoformat(res.applied_at).utcoffset() == timedelta(0)
    assert ApplyResult("filled_not_submitted", ["x"]).applied_at == ""     # nothing sent, nothing stamped


def test_a_confirmed_submit_is_recorded_on_the_queue_and_the_attempt(tmp_path, monkeypatch):
    base = make_data(tmp_path, mode="auto", switch=True)
    run_cli(base, "enqueue", "--candidates", str(tmp_path / "c.json"), "--decisions", str(tmp_path / "d.json"))

    class Ok:
        def apply(self, *a, **k):
            return ApplyResult("submitted", ["First name"],
                               confirmation_url="https://apply.test/job/1/confirmation")
    monkeypatch.setattr(cli, "pick_adapter", lambda url, allowed=None: Ok())
    assert run_cli(base, "run") == 0
    item_ = Queue(tmp_path).items["aaaa1111bbbb2222"]
    assert item_["status"] == "submitted"
    assert item_["confirmation_url"] == "https://apply.test/job/1/confirmation"
    assert datetime.fromisoformat(item_["applied_at"]).utcoffset() == timedelta(0)
    attempt = item_["attempts"][-1]
    assert attempt["outcome"] == "submitted" and attempt["applied_at"] == item_["applied_at"]
    assert attempt["confirmation_url"] == item_["confirmation_url"]


def test_dedup_an_applied_record_is_never_submitted_again(tmp_path, monkeypatch, capsys):
    base = make_data(tmp_path, mode="auto", switch=True)
    run_cli(base, "enqueue", "--candidates", str(tmp_path / "c.json"), "--decisions", str(tmp_path / "d.json"))
    calls = []

    class Ok:
        def apply(self, *a, **k):
            calls.append(1)
            return ApplyResult("submitted", ["First name"],
                               confirmation_url="https://apply.test/job/1/confirmation")
    monkeypatch.setattr(cli, "pick_adapter", lambda url, allowed=None: Ok())
    assert run_cli(base, "run") == 0 and len(calls) == 1
    # The owner approves again an item that already went out: the runner must not apply twice.
    assert run_cli(base, "approve", "aaaa11") == 0
    assert run_cli(base, "run") == 0
    assert len(calls) == 1                                  # the page was never opened a second time
    assert "already applied" in capsys.readouterr().out
    assert Queue(tmp_path).items["aaaa1111bbbb2222"]["applied_at"]


def test_run_log_counts_match_a_fake_run(tmp_path, monkeypatch):
    base = make_data(tmp_path, mode="assisted")
    plan = {                                   # what the fake adapter does for each approved job
        "https://jobs.lever.co/acme/1": "submitted",
        "https://job-boards.greenhouse.io/acme/jobs/2": Code.CONSENT_PENDING,
        "https://jobs.ashbyhq.com/acme/3": Code.NOT_FOUND,
        "https://apply.workable.com/acme/4": Code.UNKNOWN_REQUIRED_FIELD,
        "https://jobs.lever.co/acme/5": "already applied",
    }
    q = Queue(tmp_path)
    for n, url in enumerate(plan):
        q.add(f"run{n}aaaa1111", {"profile": "p", "title": "Java", "company": "Acme", "url": url,
                                  "fit": 90, "tier": "core", "confidence": "high", "cv": "general",
                                  "status": "approved"})
    q.items["run4aaaa1111"]["applied_at"] = "2026-11-01T09:00:00+00:00"    # went out earlier
    q.save()

    class Fake:
        def __init__(self, what):
            self.what = what

        def apply(self, job, *a, **k):
            if self.what == "submitted":
                return ApplyResult("submitted", [], confirmation_url="https://apply.test/job/1/confirmation")
            if self.what == "already applied":
                raise AssertionError("an applied item must never reach an adapter")
            raise ApplyFailure(self.what, "fake", "fill")
    monkeypatch.setattr(cli, "pick_adapter", lambda url, allowed=None: Fake(plan[url]))
    assert run_cli(base, "run") == 0

    from jobscan.store import FileStore
    rows = FileStore(tmp_path).read_lines("logs/runs.jsonl")
    assert len(rows) == 5
    totals = {c: sum(r[c] for r in rows) for c in ("submitted_count", "skipped_count",
                                                    "consent_pending_count", "not_found_count")}
    assert totals == {"submitted_count": 1, "skipped_count": 2,
                      "consent_pending_count": 1, "not_found_count": 1}
    assert {r["source_url"] for r in rows} == set(plan)
    assert [r["site"] for r in rows if r["consent_pending_count"]] == ["job-boards.greenhouse.io"]


def test_apply_stage_refuses_an_approved_job_from_a_blacklisted_company(tmp_path, monkeypatch):
    """ADR-005, third stage: the list changed after the job was approved, so the runner must refuse."""
    base = make_data(tmp_path, mode="assisted")
    config = tmp_path / "config.yaml"
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    cfg["blacklist"]["companies"] = ["Blocked Example"]      # the list changed after the approval
    config.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    q = Queue(tmp_path)
    q.add("cccc3333dddd4444", {"profile": "p", "title": "Java", "company": "Blocked Example",
                               "url": "https://jobs.lever.co/blocked-example/9", "fit": 90, "tier": "core",
                               "confidence": "high", "cv": "general", "status": "approved"})
    q.save()
    reached = []

    class Spy:
        def apply(self, *a, **k):
            reached.append(1)
            raise AssertionError("a blacklisted company must never reach an adapter")
    monkeypatch.setattr(cli, "pick_adapter", lambda url, allowed=None: Spy())
    assert run_cli(base, "run") == 0
    item_ = Queue(tmp_path).items["cccc3333dddd4444"]
    assert reached == [] and item_["status"] == "failed" and item_["error_code"] == "BLOCKED_BY_POLICY"
