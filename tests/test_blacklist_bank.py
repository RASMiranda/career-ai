import pytest

from jobscan.blacklist import Blacklist

# The companies the owner's batch-apply bank must never apply to, in the same shape as career-data's
# config.yaml (names and aliases only; no personal data here).
BANNED_CONFIG = [
    {"name": "Micro1", "aliases": ["Micro 1"], "domains": ["micro1.ai"]},
    {"name": "Crossing Hurdles", "aliases": ["CrossingHurdles"], "domains": ["crossinghurdles.com"]},
    {"name": "Proxify", "domains": ["proxify.io"]},
    {"name": "Alignerr", "domains": ["alignerr.com"]},
    {"name": "Recruitment Room", "aliases": ["RecruitmentRoom", "Recruitment Room - Global"],
     "domains": ["recruitmentroom.com"]},
    {"name": "Pitch N Hire", "aliases": ["pitchnhire"], "domains": ["pitchnhire.com"]},
]


@pytest.fixture
def bl():
    return Blacklist(BANNED_CONFIG)


@pytest.mark.parametrize("company", [
    "Micro1", "Micro 1", "MICRO 1 Inc.", "Crossing Hurdles", "CrossingHurdles Ltd", "Proxify AB",
    "Alignerr", "Recruitment Room - Global", "Recruitment Room Global", "RecruitmentRoom",
    "Pitch N Hire", "pitch n hire", "Pitchnhire",
])
def test_every_banned_employer_from_the_bank_is_blocked(bl, company):
    assert bl.match({"company": company}) is not None


@pytest.mark.parametrize("url", [
    "https://jobs.micro1.ai/role/1", "https://careers.crossinghurdles.com/x",
    "https://jobs.pitchnhire.com/1", "https://www.recruitmentroom.com/job",
])
def test_banned_employers_are_blocked_by_domain(bl, url):
    assert bl.match({"company": "Acme", "url": url}) is not None


def test_similar_but_different_companies_pass(bl):
    for company in ["Pitch Perfect Inc", "Micro Focus", "Alignerry Labs", "Crossing Bridges"]:
        assert bl.match({"company": company}) is None, company


def test_bank_names_load_through_from_config():
    cfg = {"blacklist": {"companies": BANNED_CONFIG}, "profiles": []}
    bl = Blacklist.from_config(cfg)
    assert len(bl) == len(BANNED_CONFIG)
    assert bl.match({"company": "Recruitment Room - Global"}) == "Recruitment Room"
