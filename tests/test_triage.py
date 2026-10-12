import pytest

from jobscan.config import ConfigError
from jobscan.triage import auto_decision, clean, reject_reason, render_brief, rules_for, triage
from jobscan.validate import validate

LONG = "We build services all day long. " * 20          # > 300 chars, no stack terms


def cand(key, title="Engineer", desc="", profile="p", **kw):
    return {"candidate_key": key, "profile": profile, "title": title, "company": "Acme",
            "url": "https://x.test/1", "description": desc, "source": "s", **kw}


def cfg(**prefilter):
    return {"profiles": [{"id": "p", "criteria": "c.md", "prefilter": prefilter}]}


def test_clean_strips_html_and_collapses_space():
    assert clean("<p>Java &amp;  Spring</p>\n<li>Angular</li>") == "Java & Spring Angular"


def test_required_terms_are_whole_words_and_only_checked_when_described():
    rules = rules_for({"prefilter": {"require_any": ["java", "ci/cd"]}})
    assert reject_reason(cand("a", desc=LONG + " JavaScript only"), rules)        # JavaScript is not java
    assert reject_reason(cand("b", desc=LONG + " we use Java daily"), rules) is None
    assert reject_reason(cand("c", desc=LONG + " strong CI/CD skills"), rules) is None
    assert reject_reason(cand("d", desc="Python dev"), rules) is None            # too short: the model decides
    assert reject_reason(cand("e", title="Java Dev", desc=LONG), rules) is None   # title counts


def test_title_rejects_are_regexes():
    rules = rules_for({"prefilter": {"reject_title": [r"\bjunior\b", "intern"]}})
    assert "junior" in reject_reason(cand("a", title="Junior Java Developer"), rules)
    assert reject_reason(cand("b", title="Senior Java Developer"), rules) is None


def test_bad_regex_is_a_config_error():
    with pytest.raises(ConfigError):
        rules_for({"id": "p", "prefilter": {"reject_title": ["("]}})


def test_no_prefilter_sends_everything_to_the_model():
    auto, to_score, deferred = triage({"candidates": [cand("a", desc=LONG)]}, {"profiles": [{"id": "p"}]})
    assert (auto, len(to_score), deferred) == ([], 1, [])


def test_cap_defers_the_rest_per_profile():
    payload = {"candidates": [cand(f"k{i}") for i in range(5)] + [cand("z", profile="q")]}
    c = {"profiles": [{"id": "p", "prefilter": {"max_to_score": 2}}, {"id": "q"}]}
    auto, to_score, deferred = triage(payload, c)
    assert [x["candidate_key"] for x in to_score] == ["k0", "k1", "z"]
    assert [x["candidate_key"] for x in deferred] == ["k2", "k3", "k4"]


def test_auto_decisions_pass_validation():
    c = cand("k1", title="Junior Dev")
    d = auto_decision(c, "title matches junior")
    ok, problems = validate({"candidates": [c]}, [d], {"active": True})
    assert problems == [] and ok[0]["disposition"] == "discarded"


def test_brief_is_compact_and_points_to_the_full_text(tmp_path):
    long = "Java " * 400
    brief = render_brief([cand("k1", desc=long, location="Lisbon", remote=True, contract_type="contract")],
                         cfg(), tmp_path, excerpt=100)
    assert "## k1 | Engineer | Acme" in brief and "Lisbon | remote | contract" in brief
    assert "pipeline show k1" in brief and len(brief) < 600           # not the 2000-char description
    assert "(no description)" in render_brief([cand("k2")], cfg(), tmp_path)


GERMAN = ("Wir suchen einen erfahrenen Entwickler für unser Team. Sie werden mit uns an der Entwicklung "
          "von Anwendungen arbeiten und die Verantwortung für die Qualität übernehmen. " * 3)
SPOKEN = {"pt-PT": "native", "en-GB": "professional", "fr-FR": "basic", "es-ES": "B1"}


def lang_rules(**kw):
    return rules_for({"id": "p", "languages": SPOKEN, "prefilter": kw})


def test_posting_written_in_unspoken_language_is_rejected():
    r = lang_rules()
    assert "written in de" in reject_reason(cand("a", desc=GERMAN), r)
    assert "written in fr" not in (reject_reason(cand("b", desc=LONG), r) or "")   # English passes
    assert reject_reason(cand("c", desc="Entwickler für unser Team"), r) is None   # too short


def test_posting_demanding_unspoken_language_is_rejected_but_plus_is_not():
    r = lang_rules()
    assert "demands de" in reject_reason(cand("a", desc=LONG + " Very good knowledge of German (C2 level)"), r)
    assert "demands fr" in reject_reason(cand("b", desc=LONG + " Fluent French required"), r)
    assert reject_reason(cand("c", desc=LONG + " German is a plus"), r) is None
    assert reject_reason(cand("d", desc=LONG + " Fluent English and Portuguese"), r) is None  # spoken


def test_working_level_is_configurable():
    assert reject_reason(cand("a", desc=LONG + " Fluent French required"), lang_rules(working_level="basic")) is None


def test_no_languages_declared_means_no_language_filter():
    r = rules_for({"id": "p", "prefilter": {}})
    assert reject_reason(cand("a", desc=GERMAN), r) is None


def test_bad_language_declaration_is_a_config_error():
    for bad in ({"xx_YY": "native"}, {"de-DE": "good"}):
        with pytest.raises(ConfigError):
            rules_for({"id": "p", "languages": bad})


# --- 2026-10-12: two Adzuna jobs that required French were emailed to a profile with fr: basic ---

FR_PROFILE = {"id": "p", "languages": {"pt-PT": "native", "en-GB": "professional", "fr-FR": "basic"}}


@pytest.mark.parametrize("text", [
    "Language Proficiency * Fluency in French is mandatory, with the ability to communicate clearly with non-IT business users.",
    "Ability to communicate clearly in French with non-technical business users.",
    "Gute Deutschkenntnisse erforderlich.",
])
def test_short_texts_that_demand_a_lacking_language_are_discarded(text):
    rules = rules_for({**FR_PROFILE, "languages": {**FR_PROFILE["languages"]}})
    assert reject_reason(cand("a", desc=text), rules)       # no length gate: a short text can still say it


def test_a_plus_and_negations_are_not_demands():
    rules = rules_for(FR_PROFILE)
    assert reject_reason(cand("a", desc="French is a plus. Java Spring Boot."), rules) is None


@pytest.mark.parametrize("location,out", [
    ("Namen, Namen (Provincie)", True), ("Tubeke, Nijvel", True), ("België", True),
    ("Brussels", False), ("Brussel, Brabant", False), ("Amsterdam", False), ("", False),
])
def test_snippet_for_an_onsite_job_where_only_lacking_languages_are_worked_is_discarded(location, out):
    rules = rules_for(FR_PROFILE)
    c = cand("a", title="Senior Java Developer", desc="Senior Java Spring Boot consultant for a client site.",
             location=location, source="adzuna")
    assert bool(reject_reason(c, rules)) is out


def test_remote_or_fully_described_jobs_keep_going_to_the_model():
    rules = rules_for(FR_PROFILE)
    assert reject_reason(cand("a", desc="Java role.", location="Namur", remote=True, source="adzuna"), rules) is None
    assert reject_reason(cand("b", desc=LONG + " Java", location="Namur", source="remotive"), rules) is None


def test_no_languages_declared_means_no_region_filtering():
    assert reject_reason(cand("a", desc="Java", location="Namur", source="adzuna"), rules_for({"id": "p"})) is None


def test_brief_marks_snippets():
    c = cand("a", desc="Java dev for a client.", source="adzuna")
    from jobscan.triage import is_snippet
    assert is_snippet(c) and not is_snippet(cand("b", desc=LONG, source="remotive"))


def test_validator_rejects_a_surfaced_job_whose_own_caution_raises_a_lacking_language():
    c = cand("k", title="Java Dev", desc="x", location="Namur")
    d = {"candidate_key": "k", "fit": 60, "tier": "core", "confidence": "low", "disposition": "low-confidence",
         "why": "Java consultancy", "caution": "French likely; onsite", "next_action": "verify"}
    config = {"profiles": [FR_PROFILE]}
    ok, problems = validate({"candidates": [c]}, [d], {"active": True}, cfg=config)
    assert any("'fr'" in p for p in problems) and not ok
    d["caution"] = "No French required; onsite"
    ok, problems = validate({"candidates": [c]}, [d], {"active": True}, cfg=config)
    assert not any("'fr'" in p for p in problems)
    d["caution"] = "French likely"; d["disposition"] = "discarded"
    ok, problems = validate({"candidates": [c]}, [d], {"active": True}, cfg=config)
    assert not any("'fr'" in p for p in problems)
