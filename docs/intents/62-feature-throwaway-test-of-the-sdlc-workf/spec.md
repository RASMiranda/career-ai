# Spec 62: Edge-case tests for truncate() (throwaway SDLC check)

## Requirements

1. Add exactly one new file, `tests/test_truncate_edges.py`. No other file changes (no `normalize.py`, docs, CI or config).
2. The file imports `truncate` from `jobscan.normalize` and contains three test functions, one per case below. Case 3 holds both of its assertions in one test.
3. Test 1: `truncate("")` and `truncate(None)` both return `""`.
4. Test 2: `truncate(" <p>Hello <b>there</b></p> ")` returns `"Hello there"` (tags removed, whitespace collapsed and stripped).
5. Test 3: `truncate("x"*10, limit=10)` returns `"x"*10` (length equal to the limit is not cut), and `truncate("one two three four", limit=9)` returns `"one two ..."` (cut at 9 characters, partial word dropped, `" ..."` appended).
6. Fixtures are synthetic strings only; no personal data, CV text or credentials.
7. `python -m pytest -q` passes with the new file.

## Acceptance criteria

- Given empty or `None` input, when `truncate` is called, then the result is `""`.
- Given `" <p>Hello <b>there</b></p> "`, when `truncate` is called with the default limit, then the result is `"Hello there"`.
- Given a 10-character string and `limit=10`, when `truncate` is called, then the string is returned unchanged.
- Given `"one two three four"` and `limit=9`, when `truncate` is called, then the result is `"one two ..."`.
- Given the finished branch, when the diff against `main` is listed, then it shows only `tests/test_truncate_edges.py` (plus the SDLC intent/spec files under `docs/intents/62-...`).
- Given a test fails against the current `normalize.py`, then it is reported and neither the test nor the code is changed to force a pass.

## Non-goals

- Any change to `normalize.py` or its behaviour.
- Other tests, docs, ADRs, CI or config.
- Merging: the PR is closed unmerged and the branch deleted.

## Concerns flagged

- None against an ADR, guardrail, privacy or safety rule. ADR-017: the issue says aiapply.co does not do this, so there is no parity question. The standing merge authorization in CLAUDE.md is deliberately not used, per the issue.
- Note for the human: the expected values were checked by reading `truncate` (line 50 to 56 of `normalize.py`) but not run at this stage.

## Test plan

- Run `python -m pytest tests/test_truncate_edges.py -q`, then the full `python -m pytest -q`.
- Confirm with `git diff --stat main` that only the allowed files changed.
- The tester role may confirm each test fails if its expected value is altered; this is optional for a throwaway.
