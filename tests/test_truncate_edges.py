from jobscan.normalize import truncate


def test_empty_and_none_return_empty_string():
    assert truncate("") == ""
    assert truncate(None) == ""


def test_tags_removed_and_whitespace_collapsed():
    assert truncate(" <p>Hello <b>there</b></p> ") == "Hello there"


def test_limit_boundary_and_word_cut():
    assert truncate("x" * 10, limit=10) == "x" * 10
    assert truncate("one two three four", limit=9) == "one two ..."
