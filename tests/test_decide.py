"""The email's "I applied" / "Not interested" links and the handler behind them (ADR-025)."""

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from jobscan import decide, report
from jobscan.apply.queue import Queue

CFG = {"profiles": [{"id": "p", "notify": {"email": ["me@mail.test"]}}]}
KEY = "76eee1ca" + "0" * 24


def make(tmp_path, status="queued"):
    q = Queue(tmp_path)
    q.add(KEY, {"title": "Senior Java", "company": "Virtual7", "url": "https://x.test/1",
                "fit": 66, "profile": "p", "status": status, "policy_notes": ["manual mode"]})
    q.save()
    return q


def test_link_prefills_an_issue_in_the_data_repo():
    u = urlparse(decide.link("me/career-data", "done", KEY))
    assert u.netloc == "github.com" and u.path == "/me/career-data/issues/new"
    assert parse_qs(u.query)["title"] == ["done 76eee1ca"]
    assert decide.link(None, "done", KEY) == "" and decide.link("me/r", "approve", KEY) == ""


@pytest.mark.parametrize("title", ["approve 76eee1ca", "done 76eee1c", "done 76eee1ca; rm -rf", "done  76eee1ca x", ""])
def test_only_done_and_skip_with_an_exact_key_are_accepted(title):
    with pytest.raises(ValueError):
        decide.parse_title(title)


def test_done_and_skip_take_the_job_out_of_the_waiting_list(tmp_path):
    make(tmp_path)
    assert "Virtual7" in decide.apply_decision(tmp_path, "done 76eee1ca")
    assert Queue(tmp_path).items[KEY]["status"] == "done"
    make(tmp_path)
    decide.apply_decision(tmp_path, "skip 76eee1ca")
    assert Queue(tmp_path).items[KEY]["status"] == "skipped"


def test_an_application_already_submitted_is_not_overwritten(tmp_path):
    make(tmp_path, "submitted")
    with pytest.raises(ValueError):
        decide.apply_decision(tmp_path, "skip 76eee1ca")


def test_the_waiting_item_in_the_email_carries_both_links(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    got = report.build_deliveries("2026-10-15", CFG, {"candidates": []}, [], make(tmp_path), out,
                                  decision_repo="me/career-data")
    body = Path(got[0]["body"]).read_text()
    assert "Waiting for your decision" in body and ">I applied<" in body and ">Not interested<" in body
    assert "title=done%2076eee1ca" in body
    plain = report.build_deliveries("2026-10-15", CFG, {"candidates": []}, [], make(tmp_path), out)
    assert "I applied" not in Path(plain[0]["body"]).read_text()


def test_repo_slug_reads_https_and_ssh_remotes():
    assert decide.REMOTE_RE.search("https://github.com/me/career-data.git").group(1) == "me/career-data"
    assert decide.REMOTE_RE.search("git@github.com:me/career-data").group(1) == "me/career-data"
