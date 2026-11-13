# Intent 70: edge-case tests for truncate() (throwaway SDLC test)

## Problem

The owner wants to exercise the SDLC workflow end to end (intent, spec, plan, build, review) with a small, safe change. `truncate()` in `src/jobscan/normalize.py` trims job descriptions before they reach the model. Its boundary behaviour is only partly covered in `tests/test_normalize.py`. From the owner's side, the need is twofold: prove the workflow works, and pin down the boundaries of `truncate()`.

## Proposed outcome

Done means a draft PR containing tests only, never merged. The tests cover four cases:

- empty string
- text exactly at the limit
- text one character over the limit
- limit 0

The build comment shows the build report first, then the review.

Out of scope:

- Any change to `truncate()` or other production code.
- Other functions in `normalize.py`.
- Changes to the workflow itself.
- Merging.

## Affected users and systems

- The owner, as the person testing the workflow.
- `tests/test_normalize.py` is the only file expected to change.
- The sdlc workflow agents (developer, tester, reviewers).
- No effect on the scan routine, profiles or data.

## Constraints

- The PR must be tests only, with no code change (the issue says so). If a test exposes a real defect, report it and do not fix it in this PR.
- The PR must stay draft and must never be merged. The CLAUDE.md "Development sessions" squash-merge authorization does not apply here.
- The sdlc agents never merge, push to `main` or change protected paths (ADR-025, docs/SDLC.md).
- Tests must not weaken existing tests or guards.
- Tests must use synthetic strings only: no personal data, CV text or credentials.
- `truncate()` guards untrusted job text before it reaches the model (ADR-003). The tests should describe current behaviour, not change it.
- `python -m pytest -q` must pass.
- No conflict with ADR-017 to ADR-022 was found. aiapply.co parity is n/a.

## Open questions

1. With limit 0 the current code returns `" ..."` for non-empty text: `text[:0]` is empty, `rsplit` gives `""`, and the suffix is appended. Should the test pin that as current behaviour, or is it a suspected defect to report separately? The tests-only constraint means the owner decides.
2. For "exact limit" and "one over": should the one-over case assert the exact output? Output depends on the last-space cut, so the test input must include spaces. Should the suffix be asserted as `" ..."`?
3. Whitespace and HTML are collapsed before the length check. Should the edge cases measure the limit on the cleaned text? That is what the code does.
4. Should existing `truncate` tests in `tests/test_normalize.py` be extended or duplicated? The tester should check for overlap.
