import pytest

from jobscan.triage import bucket

# Stand-in for the owner's apply/triage.yaml (kept generic here; the real lists live in career-data).
CFG = {
    "core_fit": ["java", "spring boot", "angular", "full stack", "tech lead", "architect",
                 "engineering manager"],
    "adjacent": ["backend", "software engineer", "platform"],
}


@pytest.mark.parametrize("title,company,snippet,expected", [
    # required by the spec
    ("SO/ Engineering Manager", "Grand Hotel Group", "", "off-domain"),
    ("Java Engineering Manager", "Acme Software", "", "core-fit"),
    ("Tech Lead (Spring Boot)", "Acme Software", "", "core-fit"),
    # off-domain words in the company or the snippet, not only the title
    ("Engineering Manager", "Acme", "Resort operations and facilities", "off-domain"),
    ("Java Developer", "Hotels Lisboa", "", "off-domain"),          # plural still matches
    ("Plant Engineering Manager", "Acme", "", "off-domain"),
    ("Mechanical Java Developer", "Acme", "", "off-domain"),
    # off-domain outranks core-fit
    ("Java Architect", "Maintenance Services Ltd", "", "off-domain"),
    # adjacent and off-target
    ("Backend Developer", "Acme", "", "adjacent"),
    ("Delivery Lead", "Acme", "Java and Spring Boot teams", "adjacent"),   # core word in text only
    ("Account Executive", "Acme", "", "off-target"),
    ("", "", "", "off-target"),
])
def test_bucket(title, company, snippet, expected):
    assert bucket(title, company, snippet, CFG) == expected


def test_no_config_means_no_owner_keywords():
    # The code ships no owner keywords: without cfg, nothing is core-fit.
    assert bucket("Java Engineering Manager", "Acme") == "off-target"


def test_owner_off_domain_words_come_from_config():
    cfg = {**CFG, "off_domain": ["casino"]}
    assert bucket("Java Developer", "Casino Digital", "", cfg) == "off-domain"
    assert bucket("Java Developer", "Acme", "", cfg) == "core-fit"


def test_keyword_is_whole_word():
    assert bucket("Javascript Developer", "Acme", "", CFG) == "off-target"
    assert bucket("Architecture Analyst", "Acme", "", CFG) == "off-target"
