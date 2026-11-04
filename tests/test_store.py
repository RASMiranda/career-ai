"""FileStore: relative names only, atomic JSON, append-only lines, corrupt data is never clobbered."""

import pytest

from jobscan.store import FileStore


def test_json_round_trip_and_default(tmp_path):
    store = FileStore(tmp_path)
    assert store.read_json("state/x.json", {"empty": True}) == {"empty": True}
    store.write_json("state/x.json", {"a": 1, "ü": "é"})
    assert FileStore(tmp_path).read_json("state/x.json") == {"a": 1, "ü": "é"}
    assert not (tmp_path / "state" / "x.json.tmp").exists()      # atomic: the temp file is renamed away


def test_append_adds_lines_and_never_rewrites_earlier_ones(tmp_path):
    store = FileStore(tmp_path)
    store.append_line("logs/runs.jsonl", {"run_id": "r1", "submitted_count": 1})
    first = (tmp_path / "logs" / "runs.jsonl").read_bytes()
    store.append_line("logs/runs.jsonl", {"run_id": "r2", "submitted_count": 0})
    after = (tmp_path / "logs" / "runs.jsonl").read_bytes()
    assert after.startswith(first) and after != first
    assert [row["run_id"] for row in store.read_lines("logs/runs.jsonl")] == ["r1", "r2"]


def test_missing_line_file_reads_as_empty(tmp_path):
    assert FileStore(tmp_path).read_lines("logs/none.jsonl") == []


def test_names_outside_the_root_are_refused(tmp_path):
    store = FileStore(tmp_path / "data")
    for name in ("", "/etc/passwd", "../outside.json", "state/../../outside.json"):
        with pytest.raises(ValueError):
            store.path(name)
    assert store.path("state/a.json") == (tmp_path / "data" / "state" / "a.json").resolve()


def test_symlink_out_of_the_root_is_refused(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "state").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        FileStore(root).path("state/a.json")


def test_corrupt_json_raises_and_is_not_overwritten_silently(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "x.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        FileStore(tmp_path).read_json("state/x.json", {})
    assert (tmp_path / "state" / "x.json").read_text(encoding="utf-8") == "{not json"
