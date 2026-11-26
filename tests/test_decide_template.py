"""The decide workflow template and the installed copy agree (ADR-026, ADR-075, issue #123).

``docs/decide-workflow.yml`` is what the owner copies into career-data/.github/workflows/decide.yml. The
installed file is not in this repo, so ``tests/fixtures/decide.installed.yml`` is a copy of it. The
comparison always runs (no environment variable, no skip). It ignores blank lines, comment lines and lines
that name a data path (the queue, the profile folders, the code checkout); any other line that differs
fails it. Refresh the fixture whenever the installed file changes.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs" / "decide-workflow.yml"
INSTALLED = ROOT / "tests" / "fixtures" / "decide.installed.yml"

# A line names a data path when it contains one of these (the queue, a profile folder, the code checkout).
PATH_LINE = re.compile(r"(profiles/|applications/|career-ai/|reports/|state/|logs/)")


def comparable(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or PATH_LINE.search(line):
            continue
        out.append(line.rstrip())
    return out


def test_the_template_stages_the_queue_under_the_profile_folders():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "git add -- 'profiles/*/applications/queue.json'" in text
    assert "git add applications/queue.json" not in text


def test_the_template_and_the_installed_copy_differ_only_in_paths_and_comments():
    assert comparable(TEMPLATE.read_text(encoding="utf-8")) == comparable(INSTALLED.read_text(encoding="utf-8"))


def test_a_difference_outside_path_names_fails_the_comparison():
    changed = TEMPLATE.read_text(encoding="utf-8").replace("concurrency: decide", "concurrency: other")
    assert comparable(changed) != comparable(INSTALLED.read_text(encoding="utf-8"))


def test_a_changed_permission_line_fails_the_comparison():
    changed = TEMPLATE.read_text(encoding="utf-8").replace("  contents: write", "  contents: read")
    assert comparable(changed) != comparable(INSTALLED.read_text(encoding="utf-8"))


def test_the_path_lines_name_the_same_paths():
    def path_lines(text: str) -> list[str]:
        return [line.strip() for line in text.splitlines() if PATH_LINE.search(line)]
    assert path_lines(TEMPLATE.read_text(encoding="utf-8")) == path_lines(INSTALLED.read_text(encoding="utf-8"))
