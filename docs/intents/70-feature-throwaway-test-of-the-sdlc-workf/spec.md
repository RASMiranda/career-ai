# Spec 70: edge-case tests for truncate() (throwaway SDLC test)

Source: `intent.md` in this folder. Tests only. Never merge.

## Requirements

1. Add tests to `tests/test_normalize.py` for `truncate(text, limit)` in `src/jobscan/normalize.py`. No other file changes.
2. Empty input: `truncate("")` returns `""`, with the default limit and with an explicit limit.
3. Exact limit: cleaned text whose length equals `limit` is returned unchanged, with no `" ..."` suffix.
4. One over: cleaned text of length `limit + 1`, containing spaces, is cut at the last space inside the first `limit` characters and ends with `" ..."`. The test asserts the exact output.
5. Limit 0: for non-empty text, `truncate("hello world", limit=0)` returns `" ..."` (current behaviour, pinned). For empty text it returns `""`.
6. The limit is measured on the cleaned text (HTML tags removed, whitespace collapsed and stripped), as the code does. At least one case shows this (for example, padding whitespace that does not count toward the limit).
7. All inputs are synthetic strings. No personal data, CV text or credentials.
8. No change to `truncate()` or any other production code, and no weakened or removed existing test.
9. `python -m pytest -q` passes.
10. The PR is draft and is never merged.

## Acceptance criteria

- Given an empty string, when `truncate("")` and `truncate("", limit=0)` are called, then both return `""`.
- Given `"a b c"` (length 5), when `truncate(text, limit=5)` is called, then the result is `"a b c"`.
- Given `"aaaa bbbb"` (length 9), when `truncate(text, limit=8)` is called, then the result is `"aaaa ..."`.
- Given `"hello world"`, when `truncate(text, limit=0)` is called, then the result is `" ..."`.
- Given `"  <b>a</b>   b  "`, which cleans to `"a b"` (length 3), when `truncate(text, limit=3)` is called, then the result is `"a b"`.
- Given the diff of the PR, when changed files are listed, then only `tests/test_normalize.py` appears.

## Non-goals

- Any change to `truncate()` or other production code, including fixing the limit-0 output.
- Tests for other functions in `normalize.py`.
- Changes to the workflow, hooks, guards or docs outside this folder.
- Merging.

## Concerns flagged

- None conflict with an ADR, guardrail, privacy or safety rule. The tests-only, never-merge constraint is consistent with ADR-025 (sdlc agents never merge or push to `main`). The CLAUDE.md "Development sessions" squash-merge authorization is deliberately not used here.
- Human decision (not an ADR conflict): limit 0 returns `" ..."`, a suffix with no content. Pinning it records current behaviour but may enshrine a defect. Decide: pin it, or open a separate issue and leave it out of this PR. This spec assumes pin it, and the comment in the test should say it is current behaviour.
- Human decision: the one-over assertion depends on the last-space cut, so it is brittle if the cut logic changes. This spec asserts the exact output.
- Note: existing `test_truncate_strips_html_and_bounds_length` partly overlaps. The new tests extend it and do not edit it.

## Test plan

- New tests in `tests/test_normalize.py`, one per criterion above, named `test_truncate_*` (empty, exact limit, one over, limit 0, limit counted on cleaned text). Use `pytest.mark.parametrize` only if it matches the existing file style.
- Run `python -m pytest -q`. Everything must pass, including the existing tests.
- Check `git diff --stat` shows only `tests/test_normalize.py`.
- The tester checks overlap with the existing truncate test. The reviewers check that no production file changed.
