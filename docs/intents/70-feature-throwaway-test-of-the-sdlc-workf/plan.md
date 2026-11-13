# Plan 70: edge-case tests for truncate() (throwaway SDLC test)

Source: `spec.md` in this folder. Tests only. Draft PR, never merge.

## Files that change (and why)

- `tests/test_normalize.py`: add `test_truncate_*` tests. Nothing else. `truncate()` is in `src/jobscan/normalize.py:50` and stays untouched. The existing import line already brings in `truncate`. The existing `test_truncate_strips_html_and_bounds_length` is not edited.

## Order of work

1. Read the existing tests in `tests/test_normalize.py` to match their style (plain functions, no parametrize unless already used).
2. Add the tests below, each with synthetic strings only.
3. Run `python -m pytest -q`, then `git diff --stat`.

## Risks

- Limit 0 returns `" ..."` for non-empty text. Pinned as current behaviour, with a comment in the test saying so. A human may prefer to drop it and open a separate defect issue.
- The one-over test asserts the exact output and depends on the last-space cut. Brittle if the cut logic changes.
- Slight overlap with the existing truncate test. Extend, do not edit.
- Scope creep: any production, workflow or doc change fails requirement 8 and the path check.

## Proof

Tests to write first (all pass against current code, since this is characterization):

- `test_truncate_empty`: `truncate("") == ""` and `truncate("", limit=0) == ""`.
- `test_truncate_exact_limit`: `truncate("a b c", limit=5) == "a b c"`.
- `test_truncate_one_over_limit`: `truncate("aaaa bbbb", limit=8) == "aaaa ..."`.
- `test_truncate_limit_zero`: `truncate("hello world", limit=0) == " ..."` (comment: current behaviour).
- `test_truncate_limit_counts_cleaned_text`: `truncate("  <b>a</b>   b  ", limit=3) == "a b"`.

Checks:

- `python -m pytest -q` is green, existing tests included.
- `git diff --stat main...HEAD` lists only `tests/test_normalize.py` (plus this intent folder's docs).
- The `pytest` check on the PR is the evidence, not the agent's report.

## Tasks

- [ ] Read `tests/test_normalize.py` and match its style
- [ ] Add `test_truncate_empty`
- [ ] Add `test_truncate_exact_limit`
- [ ] Add `test_truncate_one_over_limit`
- [ ] Add `test_truncate_limit_zero` with a comment that it pins current behaviour
- [ ] Add `test_truncate_limit_counts_cleaned_text`
- [ ] Run `python -m pytest -q`
- [ ] Confirm no production file or existing test changed
- [ ] Leave the PR as draft; do not merge

## Size

One reviewable PR: about 25 lines in one test file. No split.
