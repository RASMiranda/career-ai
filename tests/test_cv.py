from jobscan.cv import catalog, find, local_files, variant_ids
from jobscan.validate import validate


def test_ids_from_drive_style_names():
    names = ["Rui Miranda Project Manager", "Rui Miranda Resume Solutions Architect",
             "Rui Miranda Resume Tech Lead", "Rui Miranda Resume General"]
    assert sorted(variant_ids(names, "Rui").values()) == [
        "general", "project-manager", "solutions-architect", "tech-lead"]


def test_single_variant_and_plain_names():
    assert variant_ids(["CV - Ana Silva (Data)"], "Ana Silva") == {"CV - Ana Silva (Data)": "data"}
    assert variant_ids(["general", "tech-lead"]) == {"general": "general", "tech-lead": "tech-lead"}


def test_scan_prefers_pdf_and_accepts_loose_files(tmp_path):
    d = tmp_path / "cvs" / "Ana Resume Data"
    d.mkdir(parents=True)
    (d / "Ana Resume Data.docx").write_bytes(b"x")
    (d / "Ana Resume Data.pdf").write_bytes(b"x")
    (tmp_path / "cvs" / "Ana Resume Backend.docx").write_bytes(b"x")
    (tmp_path / "cvs" / "notes.txt").write_text("ignored")
    files = local_files(tmp_path, {"id": "a", "display_name": "Ana", "cv": {"dir": "cvs"}})
    assert files["data"].suffix == ".pdf" and files["backend"].suffix == ".docx"
    assert len(files) == 2


def test_catalog_is_the_text_copies(tmp_path):
    d = tmp_path / "profiles/a/cv"
    d.mkdir(parents=True)
    (d / "general.md").write_text("x"); (d / "README.md").write_text("x")
    assert list(catalog(tmp_path, {"id": "a"})) == ["general"]
    assert catalog(tmp_path, {"id": "b"}) == {}


CANDS = {"candidates": [{"candidate_key": "k1", "profile": "a", "title": "T", "company": "C",
                         "url": "https://x.test/1"}]}
DEC = {"candidate_key": "k1", "fit": 90, "tier": "core", "confidence": "high",
       "disposition": "email", "why": "w"}


def test_validate_requires_a_known_cv_for_email():
    cvs = {"a": {"general", "tech-lead"}}
    assert validate(CANDS, [{**DEC, "cv": "tech-lead"}], {"active": True}, cvs=cvs)[1] == []
    _, problems = validate(CANDS, [DEC], {"active": True}, cvs=cvs)
    assert any("no cv chosen" in p for p in problems)
    _, problems = validate(CANDS, [{**DEC, "cv": "made-up"}], {"active": True}, cvs=cvs)
    assert any("unknown cv" in p for p in problems)


def test_profile_without_cvs_needs_no_choice():
    assert validate(CANDS, [DEC], {"active": True}, cvs={"a": set()})[1] == []


def test_find_tolerates_extra_leading_words(tmp_path):
    files = {"miranda-tech-lead": tmp_path / "a.pdf", "general": tmp_path / "b.pdf"}
    assert find(files, "tech-lead") == tmp_path / "a.pdf"
    assert find(files, "general") == tmp_path / "b.pdf"
    assert find(files, "missing") is None
    assert find({"x-lead": 1, "y-lead": 2}, "lead") is None     # ambiguous
