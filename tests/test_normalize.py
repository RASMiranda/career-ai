from jobscan.normalize import candidate_key, is_http_url, norm_text, truncate


def test_accents_and_case_collapse():
    assert norm_text("Engenheiro Sénior") == norm_text("engenheiro senior")


def test_platform_noise_does_not_create_a_new_job():
    a = candidate_key("linkedin", "", "Senior Java Developer (m/f/d)", "Acme GmbH")
    b = candidate_key("linkedin", "", "Senior Java Developer", "Acme GmbH!")
    assert a == b


def test_source_id_wins_when_present():
    a = candidate_key("adzuna", "12345", "Java Dev", "Acme")
    b = candidate_key("adzuna", "12345", "Completely Different Title", "Acme")
    assert a == b


def test_different_companies_are_different_jobs():
    a = candidate_key("remotive", "", "Java Developer", "Acme")
    b = candidate_key("remotive", "", "Java Developer", "Globex")
    assert a != b


def test_key_is_stable_across_runs():
    assert candidate_key("remotive", "", "Java Dev", "Acme") == \
           candidate_key("remotive", "", "Java Dev", "Acme")


def test_url_scheme_gate():
    assert is_http_url("https://x.test/job")
    assert not is_http_url("javascript:alert(1)")
    assert not is_http_url("")


def test_truncate_strips_html_and_bounds_length():
    out = truncate("<p>hello <b>world</b></p>" + " padding" * 500, limit=50)
    assert "<" not in out and len(out) <= 60
