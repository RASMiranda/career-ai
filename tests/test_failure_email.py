"""A failed or never-submitted application must reach the owner by email, first, every day."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jobscan import report
from jobscan.apply import summary
from jobscan.apply.queue import Queue

CFG = {"profiles": [{"id": "p", "notify": {"email": ["me@mail.test"]}},
                    {"id": "q", "notify": {"email": ["you@mail.test"]}}]}
NONE = {"candidates": []}


def ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")


def queue(tmp_path, *items):
    q = Queue(tmp_path)
    for key, fields in items:
        q.add(key, {"title": "Java Lead", "company": "Acme", "url": "https://jobs.lever.co/acme/1",
                    "fit": 90, "profile": "p", "status": "queued", **fields})
    return q


def deliver(tmp_path, q, matches=None):
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    got = report.build_deliveries("2026-10-09", CFG, matches or NONE, [], q, out)
    return {d["profile"]: d for d in got}, out


def test_a_failed_application_is_emailed_first_with_reason_link_and_cv(tmp_path):
    q = queue(tmp_path, ("failed00111", {"status": "failed", "error_code": "UNKNOWN_REQUIRED_FIELD",
                                         "cv": "tech-lead", "kit": "profiles/p/03-outputs/2026-10-09-acme-java-failed001"}))
    deliveries, out = deliver(tmp_path, q)
    d = deliveries["p"]
    assert d["send"] is True and d["apply_by_hand"] == 1                  # no matches today, still emailed
    assert d["subject"] == "[Job Scan] 2026-10-09 — 0 matches — ⚠ 1 to apply by hand"
    assert d["to"] == ["me@mail.test"]
    body = Path(d["body"]).read_text()
    assert body.index("Apply by hand") < body.index("No confirmed matches today")      # first, not last
    assert "required questions" in body                                   # the plain-language reason
    assert 'href="https://jobs.lever.co/acme/1"' in body and "Open the posting and apply" in body
    assert "<b>tech-lead</b> CV" in body and "03-outputs/2026-10-09-acme-java-failed001" in body
    assert "python -m jobscan.apply done KEY" in body and "every day" in body


def test_an_approved_job_the_runner_never_submitted_is_reported_too(tmp_path):
    q = queue(tmp_path,
              ("stale0001", {"status": "approved", "updated": ago(60)}),
              ("fresh0001", {"status": "approved", "updated": ago(2), "title": "Fresh One"}))
    deliveries, _ = deliver(tmp_path, q)
    d = deliveries["p"]
    body = Path(d["body"]).read_text()
    assert d["apply_by_hand"] == 1 and d["send"] is True
    assert "approved 60 hours ago" in body.lower() or "Approved 60 hours ago" in body
    assert "has not run, or stopped" in body and "Fresh One" not in body


def test_nothing_failed_means_nothing_changes(tmp_path):
    q = queue(tmp_path)                                                    # one plain queued job
    deliveries, _ = deliver(tmp_path, q)
    d = deliveries["p"]
    assert d["apply_by_hand"] == 0 and "to apply by hand" not in d["subject"]
    assert d["subject"] == "[Job Scan] 2026-10-09 — 0 matches"
    assert "Apply by hand" not in Path(d["body"]).read_text()


def test_each_profile_only_sees_its_own_failures(tmp_path):
    q = queue(tmp_path, ("mine00001", {"status": "failed", "error_code": "CAPTCHA"}),
              ("yours0001", {"status": "failed", "error_code": "CAPTCHA", "profile": "q", "title": "Their Job"}))
    deliveries, _ = deliver(tmp_path, q)
    assert "Their Job" not in Path(deliveries["p"]["body"]).read_text()
    assert "Their Job" in Path(deliveries["q"]["body"]).read_text()
    assert deliveries["p"]["to"] == ["me@mail.test"] and deliveries["q"]["to"] == ["you@mail.test"]


def test_failure_details_are_escaped_and_unsafe_links_are_not_linked(tmp_path):
    q = queue(tmp_path, ("evil00001", {"status": "failed", "error_code": "CAPTCHA", "title": "<script>x</script>",
                                       "company": "A&B", "url": "javascript:alert(1)"}))
    body = summary.render_failures(q, "p")
    assert "<script>" not in body and "&lt;script&gt;" in body and "A&amp;B" in body
    assert "javascript:" not in body and "no link stored" in body


def test_all_failure_codes_have_a_plain_explanation(tmp_path):
    from jobscan.apply.adapters import Code
    from jobscan.apply.faillog import EXPLAIN
    codes = {v for k, v in vars(Code).items() if k.isupper()}
    assert codes <= set(EXPLAIN), codes - set(EXPLAIN)


def test_a_resolved_failure_stops_being_reported(tmp_path):
    q = queue(tmp_path, ("failed0001", {"status": "failed", "error_code": "TIMEOUT"}))
    assert summary.count_failures(q, "p") == 1
    q.set("failed0001", "done")                                            # you applied by hand
    assert summary.count_failures(q, "p") == 0 and summary.render_failures(q, "p") == ""
    deliveries, _ = deliver(tmp_path, q)
    assert deliveries["p"]["send"] is False


def test_the_markdown_summary_lists_stalled_jobs_as_well(tmp_path):
    q = queue(tmp_path, ("stale0001", {"status": "approved", "updated": ago(100)}))
    md = summary.render_markdown(q)
    assert "approved but never submitted" in md and "https://jobs.lever.co/acme/1" in md


def test_the_local_scripts_push_what_a_failed_run_recorded():
    root = Path(__file__).resolve().parents[1] / "scripts"
    sh, ps = (root / "local-apply.sh").read_text(), (root / "local-apply.ps1").read_text()
    run = next(line for line in sh.splitlines() if "jobscan.apply run" in line)
    assert "||" in run, "with `set -e` a failed run would abort before the push"
    assert "$LASTEXITCODE" in ps and ps.index("$LASTEXITCODE") < ps.index("git -C $Data add")
