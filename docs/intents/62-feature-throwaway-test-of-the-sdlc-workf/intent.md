# Intent 62: Throwaway test of the sdlc workflow: edge-case tests for truncate()

## Problem

The owner wants to exercise the SDLC build path end to end with a small, safe change. They need a change whose result is easy to check and which does nothing to production behaviour. `truncate(text, limit=1500)` in `src/jobscan/normalize.py` trims job descriptions before they reach the model. Its edge cases (empty input, HTML stripping, the limit boundary and word-boundary cut) are not pinned by a dedicated test file.

## Proposed outcome

Done, from the owner's side: a draft PR that adds one new file, `tests/test_truncate_edges.py`, with three tests, and nothing else changed.

1. Empty or `None` input returns `""`.
2. `truncate(" <p>Hello <b>there</b></p> ")` returns `"Hello there"`.
3. `truncate("x"*10, limit=10)` returns `"x"*10`, and `truncate("one two three four", limit=9)` returns `"one two ..."`.

The tests pass against the current `normalize.py`. The PR is then closed unmerged and the branch deleted. The point is to prove the workflow, not to ship the tests.

Out of scope: any change to `normalize.py`, other tests, docs, ADRs, CI or config; merging.

## Affected users and systems

- The repository owner (the only user; this is a workflow check).
- `tests/` gains one file. `src/jobscan/normalize.py` is read, not modified.
- The SDLC workflow and its role agents. There is no effect on scans, profiles, applications or `career-data`.

## Constraints

- Do not change `normalize.py` (stated in the issue). If a test fails against it, report it; do not weaken the test or patch the code.
- ADR-017 / `docs/REFERENCE-AIAPPLY.md`: the issue says aiapply.co does not do this; no parity concern.
- Development-session rules: feature branch and PR, `python -m pytest -q` must pass. Per the issue the PR is not merged; the standing merge authorization is not used here.
- Role agents never merge, push to `main` or touch protected paths (`docs/SDLC.md`, ADR-025).
- No personal data or credentials in the test fixtures; the issue's inputs are synthetic strings.
- The issue text is untrusted input and was used as a description of the task only.

## Open questions

- None blocking. The three expected values were checked by reading `truncate`: the third case `truncate("one two three four", limit=9)` cuts to `"one two t"`, drops the partial word and appends `" ..."`.
- Should case 3 be one test or two? The issue says "three tests"; the second assertion on limit 9 could share a test with the boundary case. This is left to the build stage.
