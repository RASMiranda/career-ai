import json

import pytest
import yaml

from jobscan import collect
from jobscan.blacklist import Blacklist, canon
from jobscan.models import Candidate
from jobscan.validate import validate

DEFAULT = [
    {"name": "Micro1", "aliases": ["Micro 1"], "domains": ["micro1.ai"]},
    {"name": "Crossing Hurdles", "aliases": ["CrossingHurdles"], "domains": ["crossinghurdles.com"]},
    {"name": "Proxify", "domains": ["proxify.io"]},
    {"name": "Alignerr", "domains": ["alignerr.com"]},
]


@pytest.fixture
def bl():
    return Blacklist(DEFAULT)


@pytest.mark.parametrize("company", [
    "Micro1", "MICRO1", "micro 1", "Micro1 Inc.", "micro1, LLC", "Micro One",  # last one must NOT match
])
def test_micro1_variants(bl, company):
    expected = company != "Micro One"
    assert bool(bl.match({"company": company})) is expected


@pytest.mark.parametrize("company,expected", [
    ("Proxify", True), ("Proxify AB", True), ("Proxify Talent Network", True),
    ("proxify", True), ("Proxifyd", False), ("Notproxify", False),
    ("Alignerr", True), ("Alignerr Labs", True), ("Aligner Health", False),
    ("Crossing Hurdles", True), ("CrossingHurdles Ltd", True), ("Crossing Bridges", False),
    ("Microsoft", False), ("Acme GmbH", False), ("", False),
])
def test_names(bl, company, expected):
    assert bool(bl.match({"company": company})) is expected


def test_domain_match_is_host_based(bl):
    assert bl.match({"company": "Acme", "url": "https://jobs.proxify.io/role/1"}) == "Proxify"
    assert bl.match({"company": "Acme", "url": "https://www.alignerr.com/x"}) == "Alignerr"
    assert bl.match({"company": "Acme", "url": "https://notproxify.io/x"}) is None
    assert bl.match({"company": "Acme", "url": "https://x.test/?ref=proxify.io"}) is None


def test_description_match_is_opt_in():
    job = {"company": "Acme", "title": "Dev", "description": "Hired on behalf of Proxify clients"}
    assert Blacklist(DEFAULT).match(job) is None
    assert Blacklist(DEFAULT, match_description=True).match(job) == "Proxify"


def test_plain_string_entries_and_empty_list():
    assert Blacklist(["Foo Corp"]).match({"company": "FOO"}) == "Foo Corp"
    assert Blacklist([]).match({"company": "Anything"}) is None
    assert Blacklist(None).match({"company": "Anything"}) is None


def test_from_config_merges_global_and_profile():
    cfg = {"blacklist": {"companies": ["GlobalCo"]},
           "profiles": [{"id": "a", "blacklist": {"companies": ["OnlyA"]}}, {"id": "b"}]}
    a, b = Blacklist.from_config(cfg, "a"), Blacklist.from_config(cfg, "b")
    assert a.match({"company": "OnlyA"}) and a.match({"company": "GlobalCo"})
    assert not b.match({"company": "OnlyA"}) and b.match({"company": "GlobalCo"})


def test_canon_keeps_company_names_that_are_common_words():
    assert canon("Remote") == "remote"   # unlike normalize.norm_text, which would blank it


def test_validate_rejects_blacklisted_job_that_was_not_discarded():
    cands = {"candidates": [{"candidate_key": "k", "title": "Dev", "company": "Proxify AB",
                             "url": "https://x.test/1"}]}
    dec = {"candidate_key": "k", "fit": 90, "tier": "core", "confidence": "high",
           "disposition": "email", "why": "w"}
    auth = {"active": True}
    _, problems = validate(cands, [dec], auth, Blacklist(DEFAULT))
    assert any("blacklisted" in p for p in problems)
    _, problems = validate(cands, [{**dec, "disposition": "discarded"}], auth, Blacklist(DEFAULT))
    assert problems == []


def test_collect_drops_blacklisted_jobs_before_the_model_sees_them(tmp_path, monkeypatch):
    (tmp_path / "profiles/p/01-knowledge").mkdir(parents=True)
    (tmp_path / "profiles/p/01-knowledge/05-job-match.md").write_text("x")
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({
        "blacklist": {"companies": DEFAULT},
        "profiles": [{"id": "p", "criteria": "profiles/p/01-knowledge/05-job-match.md",
                      "daily_queries": [{"source": "fake", "query": "java"}]}]}))

    def fake(query, profile, secrets=None):
        mk = lambda i, co, url: Candidate(  # noqa: E731
            candidate_key=f"k{i}", profile=profile, source="fake", title="Java Dev",
            company=co, url=url)
        return [mk(1, "Micro 1", "https://x.test/1"), mk(2, "Acme", "https://x.test/2"),
                mk(3, "Some Agency", "https://careers.proxify.io/3"), mk(4, "Globex", "https://x.test/4")]

    monkeypatch.setattr(collect, "REGISTRY", {"fake": fake})
    out = tmp_path / "c.json"
    assert collect.main(["--data", str(tmp_path), "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    assert sorted(c["company"] for c in data["candidates"]) == ["Acme", "Globex"]
    assert data["counts"]["blacklisted"] == 2
    assert data["blocked_by"] == {"Micro1": 1, "Proxify": 1}
    assert json.loads((tmp_path / "state/job-scan-seen.json").read_text()) == {} \
        if (tmp_path / "state/job-scan-seen.json").exists() else True
