"""cv-check: a changed or missing CV is named, nothing is printed but names, bad manifests fail closed."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import jobscan
from jobscan import cvcheck
from jobscan.cli import main
from jobscan.cvcheck import CvCheckError

FILES = {
    "profiles/p/cv/general.md": b"General CV text, synthetic\n",
    "profiles/p/cv/tech-lead.md": b"Tech lead CV text, synthetic\n",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_root(tmp_path: Path, files=FILES, manifest=None) -> Path:
    root = tmp_path / "data"
    root.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    if manifest is None:
        manifest = {name: digest(data) for name, data in files.items()}
    (root / "cv_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def run(root: Path, *extra) -> int:
    return main(["cv-check", "--data", str(root), *extra])


def test_a_matching_manifest_passes(tmp_path, capsys):
    root = make_root(tmp_path)
    report = cvcheck.check(root)
    assert report.fresh and report.checked == 2
    assert run(root) == 0
    assert "all 2 CV file(s) match cv_manifest.json" in capsys.readouterr().out


def test_a_changed_file_is_named_and_no_hash_is_printed(tmp_path, capsys):
    root = make_root(tmp_path)
    edited = b"General CV text, edited\n"
    (root / "profiles/p/cv/general.md").write_bytes(edited)
    assert run(root) == 1
    out = capsys.readouterr().out
    assert "changed: profiles/p/cv/general.md" in out
    assert "tech-lead" not in out                                   # the unchanged file is not named
    for value in (digest(edited), digest(FILES["profiles/p/cv/general.md"]), digest(FILES["profiles/p/cv/tech-lead.md"])):
        assert value not in out                                     # names only: no hashes, no content


def test_a_missing_file_is_named(tmp_path, capsys):
    root = make_root(tmp_path)
    (root / "profiles/p/cv/tech-lead.md").unlink()
    assert run(root) == 1
    assert "missing: profiles/p/cv/tech-lead.md" in capsys.readouterr().out


def test_no_manifest_is_an_error_not_a_pass(tmp_path, capsys):
    root = make_root(tmp_path)
    (root / "cv_manifest.json").unlink()
    assert run(root) == 2
    assert "no cv_manifest.json" in capsys.readouterr().err


def test_an_empty_manifest_is_an_error_not_a_pass(tmp_path, capsys):
    root = make_root(tmp_path, manifest={})
    assert run(root) == 2
    assert "at least one file" in capsys.readouterr().err


def test_bad_values_are_refused_and_named(tmp_path, capsys):
    for bad in ("not-a-digest", 123, "x" * 64, ""):
        root = make_root(tmp_path / str(len(str(bad))), manifest={"profiles/p/cv/general.md": bad})
        assert run(root) == 2, bad
    assert "profiles/p/cv/general.md" in capsys.readouterr().err


def test_names_outside_the_data_repo_are_refused(tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_bytes(b"not part of the data repo\n")
    for i, name in enumerate(("../outside.md", "/etc/hosts", "profiles/../../outside.md")):
        root = make_root(tmp_path / f"case{i}", files={}, manifest={name: digest(b"x")})
        try:
            cvcheck.check(root)
        except CvCheckError as exc:
            assert "outside the data repo" in str(exc) or "not a SHA-256" in str(exc)
        else:
            raise AssertionError(f"{name!r} was accepted")


def test_a_symlink_out_of_the_data_repo_is_refused(tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_bytes(b"outside\n")
    root = make_root(tmp_path, files={"profiles/p/cv/general.md": b"inside\n"})
    os.symlink(outside, root / "profiles/p/cv/leak.md")
    (root / "cv_manifest.json").write_text(json.dumps({"profiles/p/cv/leak.md": digest(b"outside\n")}),
                                           encoding="utf-8")
    try:
        cvcheck.check(root)
    except CvCheckError as exc:
        assert "outside the data repo" in str(exc)
    else:
        raise AssertionError("a symlink out of the data repo was followed")


def test_a_corrupt_manifest_is_an_error(tmp_path, capsys):
    root = make_root(tmp_path)
    (root / "cv_manifest.json").write_text("{not json", encoding="utf-8")
    assert run(root) == 2
    assert "not valid JSON" in capsys.readouterr().err


def test_a_missing_data_repo_is_an_error(tmp_path, capsys):
    assert main(["cv-check", "--data", str(tmp_path / "nowhere")]) == 2
    assert "Data repo not found" in capsys.readouterr().err


def test_large_files_are_hashed_in_full(tmp_path):
    big = bytes(range(256)) * 1024 * 3                  # 768 KiB: several read chunks
    path = tmp_path / "big.md"
    path.write_bytes(big)
    assert cvcheck.sha256_of(path) == digest(big)


def test_the_module_entry_point_runs(tmp_path):
    root = make_root(tmp_path)
    src = Path(jobscan.__file__).resolve().parent.parent
    env = {**os.environ, "PYTHONPATH": str(src)}
    done = subprocess.run([sys.executable, "-m", "jobscan", "cv-check", "--data", str(root)],
                          capture_output=True, text=True, env=env, timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    assert "all 2 CV file(s)" in done.stdout
