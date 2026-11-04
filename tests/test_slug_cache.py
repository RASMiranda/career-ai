"""Slug cache: written only after a form page answered 200; a miss is NOT_FOUND with no network guess."""

import socket
import time
import urllib.request

import pytest

from jobscan.apply import cli
from jobscan.apply.adapters import ApplyFailure, Code
from jobscan.apply.faillog import FailureLog
from jobscan.apply.greenhouse import GreenhouseRef
from jobscan.apply.queue import Queue
from jobscan.apply.slug_cache import FILE, SlugCache, locate, verify
from jobscan.store import FileStore

REF = GreenhouseRef("examplecorp", "4001", "us")


def fixed_now():
    return "2026-11-04T09:00:00+00:00"


def test_a_miss_returns_none_and_locate_says_not_found(tmp_path):
    cache = SlugCache(FileStore(tmp_path), now=fixed_now)
    assert cache.get("4001") is None
    with pytest.raises(ApplyFailure) as exc:
        locate("4001", cache)
    assert exc.value.code == Code.NOT_FOUND


def test_a_miss_makes_no_network_call(tmp_path, monkeypatch):
    def no_network(*a, **k):
        raise AssertionError("a slug-cache miss must not touch the network")
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    with pytest.raises(ApplyFailure) as exc:
        locate("4001", SlugCache(FileStore(tmp_path), now=fixed_now))
    assert exc.value.code == Code.NOT_FOUND


def test_no_slug_is_inferred_from_a_job_id(tmp_path):
    cache = SlugCache(FileStore(tmp_path), now=fixed_now)
    cache.record(REF, 200)                                   # job 4001 is verified
    assert cache.get("4002") is None                         # a neighbouring id is not inferred
    assert cache.get("4001") == {"slug": "examplecorp", "host": "us", "verified_at": fixed_now()}


def test_record_writes_only_after_http_200(tmp_path):
    for status in (0, 301, 302, 403, 404, 410, 429, 500, 503):
        root = tmp_path / str(status)
        cache = SlugCache(FileStore(root), now=fixed_now)
        assert cache.record(REF, status) is False, status
        assert not (root / FILE).exists(), status
        assert cache.get("4001") is None, status


def test_record_after_200_persists_and_survives_a_new_instance(tmp_path):
    assert SlugCache(FileStore(tmp_path), now=fixed_now).record(REF, 200) is True
    assert (tmp_path / FILE).is_file()
    again = SlugCache(FileStore(tmp_path), now=fixed_now)
    assert locate("4001", again) == REF


def test_verify_fetches_the_form_url_and_records_only_on_200(tmp_path):
    seen = []

    def status_of(url):
        seen.append(url)
        return 200

    cache = SlugCache(FileStore(tmp_path), now=fixed_now)
    assert verify(REF, cache, status_of) is True
    assert seen == [REF.form_url()]

    cache2 = SlugCache(FileStore(tmp_path / "other"), now=fixed_now)
    assert verify(REF, cache2, lambda url: 404) is False
    assert cache2.get("4001") is None


def test_a_miss_ends_in_not_found_on_the_queue(tmp_path):
    q = Queue(tmp_path)
    q.add("kkkk1111aaaa2222", {"title": "Java Lead", "company": "Examplecorp",
                               "url": "https://job-boards.greenhouse.io/examplecorp/jobs/4001",
                               "status": "approved"})
    item = q.items["kkkk1111aaaa2222"]
    try:
        locate("4001", SlugCache(FileStore(tmp_path), now=fixed_now))
    except ApplyFailure as fail:
        cli._record_failure(FailureLog(tmp_path), q, item, fail, "auto", "run0001", time.time(), False)
    assert q.items["kkkk1111aaaa2222"]["status"] == "failed"
    assert q.items["kkkk1111aaaa2222"]["error_code"] == "NOT_FOUND"
