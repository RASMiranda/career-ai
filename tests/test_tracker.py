from datetime import datetime, timedelta, timezone

import pytest

from jobscan.apply import cli, policy, summary, tracker
from jobscan.apply.queue import APPLIED, STATUSES, TRACKING, Queue
from jobscan.blacklist import Blacklist

from test_apply_core import item, make_data, run_cli

TODAY = datetime.now(timezone.utc).date()      # summary.sections() reads the real clock


def applied(tmp_path, key="k1", status="submitted", days_ago=10, **extra):
    q = Queue(tmp_path)
    q.add(key, {"title": "Java Lead", "company": "Acme", "url": "https://x.test/1", "fit": 90,
                "profile": "p", "status": "queued", **extra})
    q.set(key, status)
    stamp = f"{(TODAY - timedelta(days=days_ago)).isoformat()}T09:00:00+00:00"
    q.items[key]["applied_at"] = stamp
    if status == "submitted":
        q.items[key]["submitted_at"] = stamp
    return q


def test_tracking_statuses_are_known_and_counted_as_applied():
    assert set(TRACKING) <= set(STATUSES) and set(TRACKING) <= set(APPLIED)
    assert "queued" not in APPLIED and "failed" not in APPLIED


def test_applying_stamps_applied_at_once(tmp_path):
    q = Queue(tmp_path)
    q.add("k", {"title": "t", "company": "c", "status": "queued"})
    q.set("k", "done")
    first = q.items["k"]["applied_at"]
    q.set("k", "interview")
    assert q.items["k"]["applied_at"] == first          # tracking never moves the applied date


def test_track_records_status_and_note(tmp_path):
    q = applied(tmp_path)
    tracker.track(q, "k1", "interview", "  call on Thursday ", "2026-11-01")
    got = q.items["k1"]
    assert got["status"] == "interview" and got["follow_up_on"] == "2026-11-01"
    assert got["notes"][0]["text"] == "call on Thursday" and got["notes"][0]["status"] == "interview"


@pytest.mark.parametrize("status", ["queued", "approved", "filled", "failed", "skipped"])
def test_track_refuses_what_was_never_applied_to(tmp_path, status):
    q = Queue(tmp_path)
    q.add("k", {"title": "t", "company": "c", "status": status})
    with pytest.raises(ValueError, match="record the application first"):
        tracker.track(q, "k", "replied")


def test_track_rejects_bad_input(tmp_path):
    q = applied(tmp_path)
    with pytest.raises(ValueError):
        tracker.track(q, "k1", "hired")
    with pytest.raises(ValueError, match="date"):
        tracker.track(q, "k1", "replied", follow_up="next week")


def test_follow_up_due_after_the_wait_and_not_before(tmp_path):
    q = applied(tmp_path, days_ago=7)
    assert [i["candidate_key"] for i in tracker.follow_ups_due(q, TODAY, days=7)] == ["k1"]
    assert tracker.follow_ups_due(q, TODAY, days=8) == []


def test_follow_up_only_while_nobody_answered(tmp_path):
    q = applied(tmp_path / "a", days_ago=30)
    tracker.mark_followed_up(q, "k1")
    assert tracker.follow_ups_due(q, TODAY) == []
    q = applied(tmp_path / "b", days_ago=30)
    q.set("k1", "replied")
    assert tracker.follow_ups_due(q, TODAY) == []


def test_chosen_date_replaces_the_default_wait(tmp_path):
    q = applied(tmp_path, days_ago=30)
    q.items["k1"]["follow_up_on"] = (TODAY + timedelta(days=3)).isoformat()
    assert tracker.follow_ups_due(q, TODAY) == []
    q.items["k1"]["follow_up_on"] = TODAY.isoformat()
    assert len(tracker.follow_ups_due(q, TODAY)) == 1


def test_hand_applied_items_without_applied_at_still_get_a_date(tmp_path):
    q = Queue(tmp_path)
    q.add("k", {"title": "t", "company": "c", "status": "done", "updated": "2026-10-01T08:00:00+00:00"})
    assert len(tracker.follow_ups_due(q, TODAY)) == 1


def test_follow_up_filters_by_profile(tmp_path):
    q = applied(tmp_path, days_ago=10)
    assert tracker.follow_ups_due(q, TODAY, profile="p") and not tracker.follow_ups_due(q, TODAY, profile="x")


def test_mark_followed_up_needs_an_unanswered_application(tmp_path):
    q = applied(tmp_path, status="interview")
    with pytest.raises(ValueError, match="nobody has answered"):
        tracker.mark_followed_up(q, "k1")


def test_funnel_and_response_rate(tmp_path):
    q = Queue(tmp_path)
    for key, status in (("a", "submitted"), ("b", "done"), ("c", "interview"), ("d", "rejected"), ("e", "withdrawn")):
        q.add(key, {"title": "t", "company": key, "status": "queued", "profile": "p"})
        q.set(key, status)
    counts = tracker.funnel(q)
    assert counts["submitted"] == counts["done"] == counts["interview"] == 1
    assert tracker.response_rate(counts) == 50      # 2 of the 4 that were not withdrawn answered
    assert tracker.funnel(Queue(tmp_path / "empty")) == {}
    assert tracker.response_rate({}) is None


def test_company_with_a_live_application_is_not_auto_approved_again(tmp_path):
    q = applied(tmp_path, status="done")
    q.set("k1", "interview")
    acfg = policy.apply_cfg({"apply": {"mode": "auto"}})
    status, notes = policy.initial_status(item(company="Acme"), acfg,
                                          {"application_submission": {"allow_auto_submit": True,
                                                                      "acknowledged_on": "2026-10-15"}},
                                          q, Blacklist([]))
    assert status == "queued" and any("recently" in n for n in notes)


def test_summary_shows_funnel_in_progress_and_follow_ups(tmp_path):
    q = applied(tmp_path, "due", "submitted", days_ago=10)
    q.add("talk", {"title": "Architect", "company": "Beta", "status": "queued", "profile": "p", "fit": 80,
                   "url": "https://x.test/2"})
    q.set("talk", "done")
    tracker.track(q, "talk", "interview", "panel on Friday")
    md = summary.render_markdown(q)
    assert "**Tracker:**" in md and "2 applied" in md and "1 interview" in md
    assert "## Follow up — no answer yet" in md and "followed-up due" in md
    assert "## In progress" in md and "panel on Friday" in md
    html = summary.render_html(q, profile="p")
    assert "Follow up" in html and "In progress" in html


def test_in_progress_alone_does_not_make_an_email(tmp_path):
    q = applied(tmp_path, days_ago=1)
    q.set("k1", "interview")
    assert "In progress" in summary.render_markdown(q)
    assert summary.render_html(q, profile="p") == ""


def test_cli_track_and_followed_up(tmp_path, capsys):
    base = make_data(tmp_path)
    run_cli(base, "enqueue", "--candidates", str(tmp_path / "c.json"), "--decisions", str(tmp_path / "d.json"))
    assert run_cli(base, "track", "aaaa11", "--status", "replied") == 2        # not applied yet
    assert "record the application first" in capsys.readouterr().err
    run_cli(base, "done", "aaaa11")
    assert run_cli(base, "followed-up", "aaaa11") == 0
    assert Queue(tmp_path).items["aaaa1111bbbb2222"]["followed_up_at"]
    assert run_cli(base, "track", "aaaa11", "--status", "interview", "--note", "phone screen") == 0
    got = Queue(tmp_path).items["aaaa1111bbbb2222"]
    assert got["status"] == "interview" and got["notes"][0]["text"] == "phone screen"
    assert run_cli(base, "followed-up", "aaaa11") == 2                          # they answered
    with pytest.raises(SystemExit):                                              # not a stage
        run_cli(base, "track", "aaaa11", "--status", "hired")


def test_enqueue_keeps_the_posting_for_the_kit(tmp_path):
    import json
    base = make_data(tmp_path)
    cands = json.loads((tmp_path / "c.json").read_text())
    cands["candidates"][0]["description"] = "<p>We   need a <b>Java</b> lead.</p>" + "x" * 5000
    (tmp_path / "c.json").write_text(json.dumps(cands))
    run_cli(base, "enqueue", "--candidates", str(tmp_path / "c.json"), "--decisions", str(tmp_path / "d.json"))
    got = Queue(tmp_path).items["aaaa1111bbbb2222"]
    assert got["description"].startswith("We need a Java lead.") and len(got["description"]) == cli.DESCRIPTION_CHARS
    assert got["why"] == "w"


def test_waiting_matches_point_at_their_kit_or_how_to_get_one(tmp_path):
    q = Queue(tmp_path)
    q.add("with", {"title": "A", "company": "X", "status": "queued", "fit": 90, "url": "https://x.test/1",
                   "kit": "profiles/p/03-outputs/2026-10-08-x-a-with"})
    q.add("none", {"title": "B", "company": "Y", "status": "queued", "fit": 80, "url": "https://x.test/2"})
    md = summary.render_markdown(q)
    assert "Documents: profiles/p/03-outputs/2026-10-08-x-a-with" in md
    assert "kit prepare none" in md
