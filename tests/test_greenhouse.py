"""Greenhouse references: both hosts round-trip, malformed input is refused."""

import pytest

from jobscan.apply.greenhouse import GreenhouseRef, parse

US_URL = "https://job-boards.greenhouse.io/examplecorp/jobs/4001"
EU_URL = "https://job-boards.eu.greenhouse.io/examplecorp/jobs/4002"


def test_us_host_round_trips():
    ref = parse(US_URL)
    assert ref == GreenhouseRef("examplecorp", "4001", "us")
    assert ref.form_url() == US_URL
    assert parse(ref.form_url()) == ref


def test_eu_host_round_trips():
    ref = parse(EU_URL)
    assert ref == GreenhouseRef("examplecorp", "4002", "eu")
    assert ref.form_url() == EU_URL
    assert parse(ref.form_url()) == ref


def test_form_url_uses_the_host_the_reference_carries():
    assert GreenhouseRef("board-one", "4003", "eu").form_url() == \
        "https://job-boards.eu.greenhouse.io/board-one/jobs/4003"
    assert GreenhouseRef("board_one", "4003", "us").form_url() == \
        "https://job-boards.greenhouse.io/board_one/jobs/4003"


def test_trailing_slash_is_accepted_and_host_case_is_ignored():
    assert parse("https://JOB-BOARDS.greenhouse.io/examplecorp/jobs/4001/") == \
        GreenhouseRef("examplecorp", "4001", "us")


MALFORMED = [
    "",
    "not a url",
    "https://job-boards.greenhouse.io/",
    "https://job-boards.greenhouse.io/examplecorp",
    "https://job-boards.greenhouse.io/examplecorp/jobs/",
    "https://job-boards.greenhouse.io/examplecorp/jobs/abc",
    "https://job-boards.greenhouse.io/examplecorp/jobs/4001/apply/extra",
    "https://job-boards.greenhouse.io//jobs/4001",
    "http://job-boards.greenhouse.io/examplecorp/jobs/4001",
    "https://job-boards.greenhouse.io.example.test/examplecorp/jobs/4001",
    "https://example.test/job-boards.greenhouse.io/examplecorp/jobs/4001",
    "https://job-boards.eu.greenhouse.io:8443/examplecorp/jobs/4001",
    "https://user@job-boards.greenhouse.io/examplecorp/jobs/4001",
    "https://boards.greenhouse.io/examplecorp/jobs/4001",      # legacy host: not one of the two parsed here
]


def test_malformed_urls_raise():
    for url in MALFORMED:
        with pytest.raises(ValueError):
            parse(url)


def test_empty_slug_is_rejected_on_construction():
    with pytest.raises(ValueError):
        GreenhouseRef("", "4001", "us")
    with pytest.raises(ValueError):
        GreenhouseRef("bad slug/../x", "4001", "us")


def test_unknown_host_and_non_numeric_job_id_are_rejected():
    with pytest.raises(ValueError):
        GreenhouseRef("examplecorp", "4001", "apac")
    with pytest.raises(ValueError):
        GreenhouseRef("examplecorp", "4001a", "us")
