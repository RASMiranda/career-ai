import json

from jobscan.report import _bucket, build_deliveries, render_email, render_markdown

CANDS = {"generated_on": "2026-09-18", "errors": [], "candidates": [
    {"candidate_key": "k1", "title": "Senior Java Engineer", "company": "Acme",
     "location": "Remote", "url": "https://x.test/1", "source": "remotive",
     "contract_type": "contract", "salary": ""},
    {"candidate_key": "k2", "title": "<img src=x onerror=alert(1)>", "company": "Evil",
     "location": "", "url": "https://x.test/2", "source": "arbeitnow",
     "contract_type": "", "salary": ""},
    {"candidate_key": "k3", "title": "Thin", "company": "Vague", "url": "https://x.test/3",
     "source": "jsearch", "location": "", "contract_type": "", "salary": ""},
]}
DECS = [
    {"candidate_key": "k1", "fit": 88, "tier": "core", "confidence": "high",
     "disposition": "email", "why": "B2B remote senior Java", "caution": "",
     "next_action": "read spec"},
    {"candidate_key": "k2", "fit": 90, "tier": "core", "confidence": "high",
     "disposition": "email", "why": "x", "caution": "", "next_action": ""},
    {"candidate_key": "k3", "fit": 75, "tier": "radar", "confidence": "low",
     "disposition": "low-confidence", "why": "no description", "caution": "",
     "next_action": ""},
]


def test_buckets_split_matches_from_pending():
    matches, pending = _bucket(CANDS, DECS)
    assert [m["candidate_key"] for m in matches] == ["k2", "k1"]  # sorted by fit
    assert [p["candidate_key"] for p in pending] == ["k3"]


def test_low_fit_low_confidence_is_dropped_not_shown():
    decs = [dict(DECS[2], fit=40)]
    _, pending = _bucket(CANDS, decs)
    assert pending == []


def test_email_escapes_hostile_job_text():
    matches, pending = _bucket(CANDS, DECS)
    html_out = render_email("2026-09-18", matches, pending)
    assert "<img src=x" not in html_out
    assert "&lt;img src=x" in html_out


def test_markdown_states_nothing_was_submitted():
    matches, pending = _bucket(CANDS, DECS)
    md = render_markdown("2026-09-18", matches, pending, [])
    assert "Nothing was submitted" in md


def test_each_profile_gets_its_own_email_and_recipients(tmp_path):
    cands = {"candidates": [dict(c, profile="a") for c in CANDS["candidates"][:2]]
             + [dict(CANDS["candidates"][2], profile="b")]}
    cfg = {"profiles": [{"id": "a", "notify": {"email": ["a@mail.test"]}},
                        {"id": "b", "notify": {"email": "b@mail.test"}},
                        {"id": "c", "notify": {"email": ["c@mail.test"]}}]}
    out = {d["profile"]: d for d in build_deliveries("2026-09-18", cfg, cands, DECS,
                                                    out_dir=tmp_path)}
    assert out["a"]["to"] == ["a@mail.test"] and out["a"]["matches"] == 2
    assert out["b"]["to"] == ["b@mail.test"] and out["b"]["pending"] == 1
    assert out["c"]["send"] is False                 # nothing to report, no email
    assert "Senior Java Engineer" not in (tmp_path / "email-b.html").read_text(encoding="utf-8")
    assert out["a"]["subject"] == "[Job Scan] 2026-09-18 — 2 matches"
    json.dumps(list(out.values()))                   # manifest is serialisable


def test_applications_section_only_shows_that_profiles_queue(tmp_path):
    from jobscan.apply.queue import Queue
    q = Queue(tmp_path)
    for key, prof, title in [("aaaa1111", "a", "Only-A role"), ("bbbb2222", "b", "Only-B role")]:
        q.add(key, {"profile": prof, "title": title, "company": "X", "fit": 90,
                    "url": "https://x.test", "status": "queued"})
    cfg = {"profiles": [{"id": "a", "notify": {"email": ["a@mail.test"]}},
                        {"id": "b", "notify": {"email": ["b@mail.test"]}}]}
    build_deliveries("2026-09-18", cfg, {"candidates": []}, [], q, tmp_path)
    a = (tmp_path / "email-a.html").read_text(encoding="utf-8")
    assert "Only-A role" in a and "Only-B role" not in a
