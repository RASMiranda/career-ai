"""--profile on every apply subcommand that acts on one profile (issue: apply --profile, ADR-069 c, ADR-078).

Profile ids are fixtures only (``ana``, ``bruno``); candidate rows and applicant values are synthetic.
"""

import json

import yaml

from jobscan.apply import cli
from jobscan.apply.queue import Queue
from profile_helpers import ensure_profile, write_apply_config, write_profile

KEY_ANA = "aaaa1111bbbb2222"
KEY_BRUNO = "cccc3333dddd4444"
KEY_ANA_2 = "eeee5555ffff6666"


def _authorization(root, pid, active=True):
    path = root / "profiles" / pid / "authorization.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"active": active,
                                    "application_submission": {"master_switch": False, "acknowledged_on": ""}}),
                    encoding="utf-8")


def setup_data(root, pids=("ana",), mode="manual", authorized=None):
    (root / "config.yaml").write_text(yaml.safe_dump({"blacklist": {"companies": []}}), encoding="utf-8")
    for pid in pids:
        write_profile(root, pid, {"applicant": {"first_name": "Test", "last_name": "Person",
                                                "email": "test@example.test"}})
        write_apply_config(root, pid, {"mode": mode})
        if authorized is None or pid in authorized:
            _authorization(root, pid)
    return ["--data", str(root)]


def candidates(root, rows):
    """rows: (key, profile or None). Writes candidates.json and decisions.json, all emailable."""
    cands = [{"candidate_key": k, "profile": p, "source": "s", "title": "Java Lead", "company": f"Co {k[:4]}",
              "url": f"https://jobs.lever.co/co/{k[:4]}"} for k, p in rows]
    decs = [{"candidate_key": k, "fit": 90, "tier": "core", "confidence": "high", "disposition": "email",
             "why": "w", "cv": ""} for k, _ in rows]
    (root / "c.json").write_text(json.dumps({"candidates": cands}), encoding="utf-8")
    (root / "d.json").write_text(json.dumps(decs), encoding="utf-8")
    return ["--candidates", str(root / "c.json"), "--decisions", str(root / "d.json")]


def enqueue(base, cand_args, *extra):
    return cli.main([*base, "enqueue", *cand_args, *extra])


# ---------------------------------------------------------------- one profile

def test_one_profile_without_a_flag_is_unchanged(tmp_path):
    ensure_profile(tmp_path, "ana")
    base = setup_data(tmp_path)
    args = candidates(tmp_path, [(KEY_ANA, "ana"), (KEY_ANA_2, None)])
    assert enqueue(base, args) == 0
    assert set(Queue(tmp_path, "ana").items) == {KEY_ANA, KEY_ANA_2}
    assert Queue(tmp_path, "ana").items[KEY_ANA_2]["profile"] == "ana"


# ------------------------------------------------------------ several profiles

def test_enqueue_routes_each_row_to_its_own_profile(tmp_path):
    for pid in ("ana", "bruno"):
        ensure_profile(tmp_path, pid)
    base = setup_data(tmp_path, pids=("ana", "bruno"))
    args = candidates(tmp_path, [(KEY_ANA, "ana"), (KEY_BRUNO, "bruno")])
    assert enqueue(base, args) == 0
    assert set(Queue(tmp_path, "ana").items) == {KEY_ANA}
    assert set(Queue(tmp_path, "bruno").items) == {KEY_BRUNO}


def test_enqueue_row_without_a_profile_and_no_flag_is_refused(tmp_path):
    for pid in ("ana", "bruno"):
        ensure_profile(tmp_path, pid)
    base = setup_data(tmp_path, pids=("ana", "bruno"))
    args = candidates(tmp_path, [(KEY_ANA, "ana"), (KEY_BRUNO, None)])
    assert enqueue(base, args) == 2
    assert Queue(tmp_path, "ana").items == {} and Queue(tmp_path, "bruno").items == {}


def test_enqueue_flag_that_disagrees_with_a_row_refuses_the_whole_file(tmp_path, capsys):
    for pid in ("ana", "bruno"):
        ensure_profile(tmp_path, pid)
    base = setup_data(tmp_path, pids=("ana", "bruno"))
    args = candidates(tmp_path, [(KEY_ANA, "ana"), (KEY_BRUNO, "bruno")])
    assert enqueue(base, args, "--profile", "ana") == 2
    assert "bruno" in capsys.readouterr().err
    assert Queue(tmp_path, "ana").items == {}                 # the good row is not written either
    assert Queue(tmp_path, "bruno").items == {}


def test_enqueue_flag_fills_a_row_without_a_profile(tmp_path):
    for pid in ("ana", "bruno"):
        ensure_profile(tmp_path, pid)
    base = setup_data(tmp_path, pids=("ana", "bruno"))
    args = candidates(tmp_path, [(KEY_ANA, None)])
    assert enqueue(base, args, "--profile", "ana") == 0
    assert Queue(tmp_path, "ana").items[KEY_ANA]["profile"] == "ana"


def test_enqueue_reads_authorization_of_the_row_profile(tmp_path):
    for pid in ("ana", "bruno"):
        ensure_profile(tmp_path, pid)
    base = setup_data(tmp_path, pids=("ana", "bruno"), mode="assisted", authorized=("ana",))
    args = candidates(tmp_path, [(KEY_ANA, "ana"), (KEY_BRUNO, "bruno")])
    assert enqueue(base, args) == 2                           # bruno has no authorization.yaml: fails closed
    assert Queue(tmp_path, "ana").items == {} and Queue(tmp_path, "bruno").items == {}


def test_summary_with_a_profile_writes_only_that_profile(tmp_path):
    for pid in ("ana", "bruno"):
        ensure_profile(tmp_path, pid)
    base = setup_data(tmp_path, pids=("ana", "bruno"))
    assert cli.main([*base, "summary", "--profile", "ana"]) == 0
    assert (tmp_path / "profiles/ana/reports/applications.md").is_file()
    assert not (tmp_path / "profiles/bruno/reports/applications.md").exists()


def test_approve_with_a_key_from_another_profile_changes_nothing(tmp_path):
    for pid in ("ana", "bruno"):
        ensure_profile(tmp_path, pid)
    base = setup_data(tmp_path, pids=("ana", "bruno"))
    enqueue(base, candidates(tmp_path, [(KEY_BRUNO, "bruno")]))
    assert cli.main([*base, "approve", "--profile", "ana", KEY_BRUNO[:6]]) == 2
    assert Queue(tmp_path, "bruno").items[KEY_BRUNO]["status"] == "queued"


def test_approve_with_a_profile_works_on_that_queue(tmp_path):
    for pid in ("ana", "bruno"):
        ensure_profile(tmp_path, pid)
    base = setup_data(tmp_path, pids=("ana", "bruno"))
    enqueue(base, candidates(tmp_path, [(KEY_BRUNO, "bruno")]))
    assert cli.main([*base, "approve", "--profile", "bruno", KEY_BRUNO[:6]]) == 0
    assert Queue(tmp_path, "bruno").items[KEY_BRUNO]["status"] == "approved"


def test_track_without_a_profile_is_refused_with_several(tmp_path, capsys):
    for pid in ("ana", "bruno"):
        ensure_profile(tmp_path, pid)
    base = setup_data(tmp_path, pids=("ana", "bruno"))
    assert cli.main([*base, "track", KEY_ANA[:6], "--status", "replied"]) == 2
    assert "--profile" in capsys.readouterr().err


def test_an_unknown_profile_is_exit_2(tmp_path):
    ensure_profile(tmp_path, "ana")
    base = setup_data(tmp_path)
    assert cli.main([*base, "approve", "--profile", "nobody", KEY_ANA]) == 2


def test_run_still_needs_a_profile_with_several(tmp_path):
    for pid in ("ana", "bruno"):
        ensure_profile(tmp_path, pid)
    base = setup_data(tmp_path, pids=("ana", "bruno"))
    assert cli.main([*base, "run"]) == 2


def test_blacklist_and_bundle_need_no_profile_with_several(tmp_path, capsys):
    for pid in ("ana", "bruno"):
        ensure_profile(tmp_path, pid)
    base = setup_data(tmp_path, pids=("ana", "bruno"))
    assert cli.main([*base, "blacklist", "list"]) == 0
    assert cli.main([*base, "bundle", "--out", str(tmp_path / "f.md")]) == 0
    assert "no failures" in capsys.readouterr().out
