import json

import pytest

from jobscan import clip, redact

PAGE = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta name="csrf-token" content="SECRET-CSRF"><meta property="og:url" content="https://board.test/jobs/9?trk=abc#top">
<meta name="member-id" content="urn:li:member:12345">
<link rel="canonical" href="https://board.test/jobs/9?utm=1"><link rel="stylesheet" href="/x.css">
<title>Senior Java Lead - Acme | Ana Silva</title>
<style>.x{color:red}</style>
<script>window.session = "JSESSIONID=abcdef"; fetch('/api?token=t')</script>
<script type="application/ld+json">{"@type":"JobPosting","title":"Senior Java Lead","datePosted":"2026-10-05",
"description":"Lead the platform team and mentor developers across the company, contact jobs@acme.test today.",
"hiringOrganization":{"name":"Acme"},"url":"https://board.test/jobs/9"}</script>
<noscript><img src="https://tracker.test/p.gif"></noscript>
</head><body onload="steal()" style="background:url(x)">
<!-- member 12345 viewed this -->
<svg width="10"><path d="M0"/><g><text>icon</text></g></svg>
<nav aria-label="Ana Silva profile"><a href="https://www.linkedin.com/in/ana-silva-123/?trk=nav#x" title="Ana's profile">Ana Silva</a></nav>
<img src="data:image/png;base64,AAAA" alt="Photo of ana silva" data-member-id="12345">
<form action="/apply?session=abc" method="post" data-testid="apply-form" data-tracking-id="zz9">
<label for="fn">First name</label><input id="fn" name="fn" type="text" value="Ana" required>
<input type="email" name="em" value="ana.private@mail.test"><input type="hidden" name="csrf" value="TOKEN">
<input type="tel" value="+351 912 345 678"><input name="noType" value="typeless">
<input type="radio" name="auth" value="yes" checked> Yes <input type="checkbox" name="c" value="agree">
<select name="lvl"><option value="1">Junior</option><option value="2" selected>Senior</option></select>
<textarea name="msg">Dear team, I live in Lisbon &amp; my number is 912345678</textarea>
<button type="submit" value="Send">Send &nbsp;application</button></form>
<p>Call +44 7700 900123 or write to ana@home.test. Posted 2026-10-05. Q&amp;A in Lisbon, Portugal.</p>
<script async src="https://cdn.test/app.js"></script></body></html>"""


def run(terms=("Ana", "Silva", "Lisbon")):
    return redact.redact(PAGE, list(terms))


def test_removes_scripts_styles_comments_and_session_data():
    out, counts = run()
    for gone in ("JSESSIONID", "SECRET-CSRF", "token=t", "tracker.test", "color:red", "member 12345",
                 "steal()", "cdn.test", "<path", "<noscript", "<style", "background:url"):
        assert gone not in out, gone
    assert counts["scripts_removed"] == 2 and counts["comments_removed"] == 1 and counts["svg_removed"] == 1


def test_keeps_the_structure_an_adapter_needs():
    out, _ = run()
    for kept in ('<!DOCTYPE html>', 'charset="utf-8"', 'name="viewport"', 'data-testid="apply-form"',
                 '<label for="fn">First name</label>', '<option value="2" selected>Senior</option>',
                 '<option value="1">Junior</option>', 'type="radio"', 'value="yes"', 'value="agree"',
                 'type="submit"', 'value="Send"', 'rel="canonical"', "&nbsp;application", "&amp;"):
        assert kept in out, kept


def test_blanks_what_the_person_typed_but_not_the_option_values():
    out, counts = run()
    for gone in ("ana.private", "912 345 678", "TOKEN", "typeless", "Dear team", "912345678"):
        assert gone not in out, gone
    assert 'name="fn" type="text" value=""' in out or 'value=""' in out
    assert counts["inputs_blanked"] == 5 and counts["textareas_blanked"] == 1


def test_removes_contact_details_and_every_term_case_insensitively():
    out, _ = run()
    assert "[phone]" in out and "[email]" in out and "ana@home.test" not in out
    for term in ("Ana", "Silva", "ana silva", "Lisbon", "ana-silva"):
        assert term.lower() not in out.lower().replace("senior java", ""), term
    assert out.count("REDACTED") >= 4
    assert "Posted 2026-10-05" in out and '"datePosted":"2026-10-05"' in out      # dates are not phone numbers


def test_trims_urls_and_profile_ids():
    out, _ = run()
    assert "linkedin.com/in/REDACTED" in out and "ana-silva" not in out
    assert 'href="https://board.test/jobs/9"' in out and "utm=1" not in out and "trk=abc" not in out
    assert 'action="/apply"' in out
    assert "urn:li:member" not in out and "data-tracking-id" not in out and "data-member-id" not in out
    assert "onload" not in out and 'style="' not in out


def test_json_ld_survives_so_clip_still_reads_a_redacted_page():
    out, _ = run(terms=())
    (job,) = clip.parse(out, "p")
    assert job.title == "Senior Java Lead" and job.company == "Acme" and job.url == "https://board.test/jobs/9"
    assert "[email]" in job.description and "jobs@acme.test" not in job.description
    assert job.posted_at == "2026-10-05"


def test_is_idempotent_and_tolerates_broken_markup():
    once, _ = run()
    twice, _ = redact.redact(once, ["Ana", "Silva", "Lisbon"])
    assert twice == once
    messy = "<div><p>unclosed <b>bold <input disabled value=abc><span class=x>text"
    out, _ = redact.redact(messy, [])
    assert "text" in out and 'value=""' in out and "abc" not in out


def test_terms_with_regex_characters_are_literal():
    out, _ = redact.redact("<p>Works at C++ Corp (the one) and A.B.</p>", ["C++", "(the one)", "A.B."])
    assert out.count("REDACTED") == 3 and "C++" not in out


# ------------------------------------------------------------------------ cli
def test_cli_writes_next_to_the_original_and_warns_without_terms(tmp_path, capsys):
    src = tmp_path / "page.html"
    src.write_text(PAGE)
    assert redact.main([str(src)]) == 0
    out = capsys.readouterr().out
    assert "no --term given" in out and "read it before you share it" in out
    safe = (tmp_path / "page.redacted.html").read_text()
    assert "ana.private" not in safe and src.read_text() == PAGE
    assert redact.main([str(src), "--term", "Ana", "--out", str(tmp_path / "o.html")]) == 0
    assert "no --term given" not in capsys.readouterr().out


def test_cli_refuses_bad_input(tmp_path, capsys):
    src = tmp_path / "page.html"
    src.write_text(PAGE)
    assert redact.main([str(src), "--out", str(src)]) == 2
    assert "overwrite the original" in capsys.readouterr().err
    mhtml = tmp_path / "page.mhtml"
    mhtml.write_text("From: <Saved by Blink>\nMIME-Version: 1.0\nContent-Type: multipart/related\n\n--x")
    assert redact.main([str(mhtml)]) == 2
    assert ".mhtml" in capsys.readouterr().err
    assert redact.main([str(tmp_path / "missing.html")]) == 2
