"""Build guard: no personal data in career-ai (ADR-046, CLAUDE.md "Never commit personal data here").

Two layers:
- Generic shapes (email addresses, international phone numbers) are checked in every tracked file
  and always run.
- Owner-specific strings (names, phone numbers, addresses) are never written in this repo. They are
  read at test time from the file named by ``CAREER_PII_PATTERNS_FILE``, or from the ignored local
  file ``tests/local/pii_patterns.txt``: one literal per line, matched case-insensitively. CI gets
  them from a repository secret (owner action). Without them that layer is skipped, not passed.

Failure messages name the file and the line number, never the matched text.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOCAL_FILE = ROOT / "tests" / "local" / "pii_patterns.txt"

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}")
# Reserved test domains (RFC 2606 / 6761) and organisation domains that are not personal.
PLACEHOLDER_DOMAINS = (".test", ".invalid", ".example", "example.com", "example.org", "example.net",
                       "anthropic.com", "github.com", "users.noreply.github.com")
PHONE = re.compile(r"(?<![\w/.])\+\d{1,3}[ .\-]?\(?\d[\d .()\-]{6,}\d(?!\w)")


def tracked_files():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.splitlines() if p and not p.startswith("tests/local/")]


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="ignore")


def test_no_email_addresses_in_tracked_files():
    hits = []
    for path in tracked_files():
        for n, line in enumerate(read_text(path).splitlines(), start=1):
            for m in EMAIL.finditer(line):
                if not m.group(0).lower().endswith(PLACEHOLDER_DOMAINS):
                    hits.append(f"{path.relative_to(ROOT)}:{n}")
    assert not hits, "email address found (use a .test or example.com address in fixtures): " + ", ".join(hits)


def test_no_international_phone_numbers_in_non_test_files():
    # Test fixtures hold phone-shaped strings on purpose (redaction tests). Real numbers are caught
    # by the owner-pattern layer below in every file, tests included.
    hits = []
    for path in tracked_files():
        if path.relative_to(ROOT).parts[0] == "tests":
            continue
        for n, line in enumerate(read_text(path).splitlines(), start=1):
            if PHONE.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{n}")
    assert not hits, "phone-like number found: " + ", ".join(hits)


def owner_patterns():
    env = os.environ.get("CAREER_PII_PATTERNS_FILE")
    path = Path(env) if env else LOCAL_FILE
    if not path.is_file():
        return None
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def test_no_owner_identity_strings_in_tracked_files():
    patterns = owner_patterns()
    if not patterns:
        pytest.skip("no owner pattern file: set CAREER_PII_PATTERNS_FILE (CI secret) to enforce this layer")
    hits = []
    for path in tracked_files():
        text = read_text(path).lower()
        for n, line in enumerate(text.splitlines(), start=1):
            for index, pattern in enumerate(patterns, start=1):
                if pattern.lower() in line:
                    hits.append(f"{path.relative_to(ROOT)}:{n} (pattern {index})")
    assert not hits, "owner identity string found: " + ", ".join(hits)
