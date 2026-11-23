"""The review stage's output contract, its checks and the PR's risk tier (ADR-067).

Pure: no file, no git, no model, no ``eval``. ``sdlc_engine/__init__.py`` reads the files and calls these functions.
The contract the reviewer writes to ``.sdlc/review.md``:

    line 1      ``Nothing to fix.``  or  ``N findings (I important, M nit, P pre-existing)``
    then        one line per finding: ``IMPORTANT|NIT|PRE-EXISTING path:line - text``, line = 12 or 10-20
    last        optional ``Checks: ...``, which the workflow replaces with the first line of .sdlc/checks.txt

Anything else is malformed and fails closed: the review becomes one IMPORTANT finding, ``unparseable review``.
"""

import re

MAX_FINDINGS = 50                  # more finding lines than this is malformed
MAX_LINE = 300                     # a longer line is malformed
MAX_REVIEW_BYTES = 20_000          # a longer file is malformed; the posted review stays under this too
NOTHING = "Nothing to fix."
COUNT_RE = re.compile(r"(\d{1,3}) findings \((\d{1,3}) important, (\d{1,3}) nit, (\d{1,3}) pre-existing\)")
FINDING_RE = re.compile(r"(IMPORTANT|NIT|PRE-EXISTING) (\S+):(\d{1,6})(?:-(\d{1,6}))? - (.+)")
HUNK_RE = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
UNPARSEABLE = {"tag": "IMPORTANT", "path": ".sdlc/review.md", "lo": 1, "hi": 1, "text": "unparseable review"}


def _bad(why: str) -> dict:
    return {"ok": False, "why": why, "nothing": False, "findings": []}


def parse(text: str) -> dict:
    """The findings of a review file, or ``ok: False`` with the reason. Never raises on any input."""
    if len(text.encode("utf-8", "replace")) > MAX_REVIEW_BYTES:
        return _bad(f"larger than {MAX_REVIEW_BYTES} bytes")
    lines = [line.rstrip() for line in text.splitlines()]
    head = lines[0] if lines else ""
    expected = None
    nothing = head == NOTHING
    if not nothing:
        m = COUNT_RE.fullmatch(head)
        if not m:
            return _bad("line 1 is neither 'Nothing to fix.' nor the count line")
        total, important, nit, pre = (int(g) for g in m.groups())
        if total == 0 or total != important + nit + pre:
            return _bad("the count line does not add up")
        expected = (important, nit, pre)
    body = lines[1:]
    last = max((i for i, line in enumerate(body) if line.strip()), default=-1)
    findings, checks_seen = [], False
    for i, line in enumerate(body):
        if not line.strip():
            continue
        if len(line) > MAX_LINE:
            return _bad(f"line {i + 2} is longer than {MAX_LINE} characters")
        if line.startswith("Checks: ") and i == last and not checks_seen:
            checks_seen = True                      # replaced by the workflow's own value; its text is not used
            continue
        m = FINDING_RE.fullmatch(line)
        if not m:
            return _bad(f"line {i + 2} is not a finding")
        tag, path, lo, hi, what = m.groups()
        lo = int(lo)
        hi = int(hi) if hi else lo
        if lo < 1 or hi < lo:
            return _bad(f"line {i + 2} has an impossible line range")
        findings.append({"tag": tag, "path": path, "lo": lo, "hi": hi, "text": what})
        if len(findings) > MAX_FINDINGS:
            return _bad(f"more than {MAX_FINDINGS} findings")
    if nothing and findings:
        return _bad("says nothing to fix but lists findings")
    if expected is not None:
        counted = (sum(f["tag"] == "IMPORTANT" for f in findings), sum(f["tag"] == "NIT" for f in findings),
                   sum(f["tag"] == "PRE-EXISTING" for f in findings))
        if counted != expected:
            return _bad("the count line disagrees with the findings")
    return {"ok": True, "why": "", "nothing": nothing, "findings": findings}


def hunk_ranges(patch: str) -> dict:
    """path -> [(first, last)] of the new file's lines that a hunk covers: changed lines and their context.

    Hunk bodies are counted, not guessed from their first character, so an added line such as ``++ x`` (which reads
    ``+++ x``) is body text, never a file header. A deleted file (``+++ /dev/null``) has no new lines and no range."""
    ranges, path, old_left, new_left = {}, None, 0, 0
    for line in patch.splitlines():
        if old_left or new_left:
            if line.startswith("-"):
                old_left -= 1
            elif line.startswith("+"):
                new_left -= 1
            elif line.startswith("\\"):
                pass                                    # "\ No newline at end of file"
            else:
                old_left -= 1
                new_left -= 1
            continue
        if line.startswith("+++ "):
            name = line[4:].split("\t")[0]
            path = None if name == "/dev/null" else (name[2:] if name.startswith("b/") else name)
        elif line.startswith("@@"):
            m = HUNK_RE.match(line)
            if not m:
                continue
            old_start, old_count, new_start, new_count = m.groups()
            old_left = int(old_count) if old_count is not None else 1
            new_left = int(new_count) if new_count is not None else 1
            if path is not None and new_left:
                ranges.setdefault(path, []).append((int(new_start), int(new_start) + new_left - 1))
    return ranges


def in_diff(path: str, lo: int, hi: int, ranges: dict) -> bool:
    """A finding is kept when its line (or any line of its range) is inside a hunk's new-side range."""
    return any(lo <= last and first <= hi for first, last in ranges.get(path, []))


def decide(text: str, ranges, checks: str) -> dict:
    """What the review posts. ``ranges`` None means no diff could be read: nothing is dropped and the summary says so.

    Dropped: an IMPORTANT or NIT whose line is not in the diff. PRE-EXISTING is never checked against the diff.
    ``needs_changes`` is true only for a kept IMPORTANT finding; it chooses wording and nothing else."""
    parsed = parse(text)
    dropped = []
    if not parsed["ok"]:
        kept, why = [dict(UNPARSEABLE)], parsed["why"]
    else:
        why, kept = "", []
        for finding in parsed["findings"]:
            if finding["tag"] == "PRE-EXISTING" or ranges is None or in_diff(finding["path"], finding["lo"],
                                                                              finding["hi"], ranges):
                kept.append(finding)
            else:
                dropped.append(finding)
    return {"findings": kept, "dropped": dropped, "needs_changes": any(f["tag"] == "IMPORTANT" for f in kept),
            "unparseable": why, "no_diff": ranges is None, "text": render(kept, checks)}


def _span(finding: dict) -> str:
    return str(finding["lo"]) if finding["lo"] == finding["hi"] else f"{finding['lo']}-{finding['hi']}"


def render(findings: list, checks: str) -> str:
    """The posted review: the contract shape, rebuilt from the findings that were kept, then the Checks line."""
    if findings:
        count = {tag: sum(f["tag"] == tag for f in findings) for tag in ("IMPORTANT", "NIT", "PRE-EXISTING")}
        lines = [f"{len(findings)} findings ({count['IMPORTANT']} important, {count['NIT']} nit, "
                 f"{count['PRE-EXISTING']} pre-existing)"]
        lines += [f"{f['tag']} {f['path']}:{_span(f)} - {f['text']}" for f in findings]
    else:
        lines = [NOTHING]
    return "\n".join(lines + [f"Checks: {checks}"]) + "\n"


def summary(result: dict, changed) -> str:
    """The step summary's lines. Built from tags, line numbers and counts only: a finding's own text and any path that is
    not a changed file are never printed, because the job summary is not agent output (tests/test_sdlc_config.py)."""
    out = []
    if result["unparseable"]:
        out.append(f"- Review unparseable ({result['unparseable']}): posted as one IMPORTANT finding.")
    if result["no_diff"]:
        out.append("- No diff file: findings were not checked against the diff.")
    for f in result["dropped"]:
        where = f["path"] if changed is not None and f["path"] in changed else "a path outside the diff"
        out.append(f"- Dropped, not on a changed line: {f['tag']} at {where}:{_span(f)}.")
    return ("\n".join(out) + "\n") if out else ""


def next_gate(stage: str, needs_changes: bool):
    """The 'Next gate' sentence after a review. None for other stages, which keep their own sentence."""
    if stage == "build":
        return ("Fix or dismiss each Important finding, then apply `agent:build` again. A human merges." if needs_changes
                else "No Important finding in the review above. Read the draft PR; a human merges.")
    if stage == "review":
        return ("Fix or dismiss each Important finding. A human merges." if needs_changes
                else "No Important finding. A human decides and merges.")
    return None


# --------------------------------------------------------------------------- risk tier (ADR-067)
def _is_docs(path: str) -> bool:
    return path.startswith("docs/") or path.endswith(".md")


def _is_tests(path: str) -> bool:
    return path.startswith("tests/")


def _listed(paths: list) -> str:
    shown = ", ".join(f"`{p.replace('`', '')}`" for p in paths[:3])
    return shown + (f" and {len(paths) - 3} more" if len(paths) > 3 else "")


def risk_tier(paths, is_protected):
    """(tier, one-line reason) from the changed paths alone; ``is_protected`` is the project's protected-path test.

    HIGH: a protected path changed, or no path could be read. LOW: only docs (``docs/**`` or any Markdown file) and
    tests changed. MEDIUM: anything else. The author never enters this."""
    paths = sorted({p for p in paths if p})
    if not paths:
        return "HIGH", "no changed files could be read"
    protected = [p for p in paths if is_protected(p)]
    if protected:
        return "HIGH", "a protected path changed: " + _listed(protected)
    code = [p for p in paths if not (_is_docs(p) or _is_tests(p))]
    if not code:
        return "LOW", "only docs and tests changed"
    return "MEDIUM", "code outside the protected paths changed: " + _listed(code)
