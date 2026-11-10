# Plan 62: Edge-case tests for truncate() (throwaway SDLC check)

## Files that change (and why)

- `tests/test_truncate_edges.py` (new): the only code file. Three tests for `truncate` in `src/jobscan/normalize.py` (lines 50-56).
- `docs/intents/62-.../` intent, spec, plan: SDLC records only.
- Not touched: `normalize.py`, `tests/test_normalize.py`, docs, CI, config.

## Order of work

1. Create `tests/test_truncate_edges.py` with `from jobscan.normalize import truncate` (same import style as `tests/test_normalize.py`).
2. Write the three tests (plain functions, no fixtures, synthetic strings only):
   - `test_empty_and_none_return_empty_string`: `truncate("") == ""` and `truncate(None) == ""`.
   - `test_tags_removed_and_whitespace_collapsed`: `truncate(" <p>Hello <b>there</b></p> ") == "Hello there"`.
   - `test_limit_boundary_and_word_cut`: `truncate("x"*10, limit=10) == "x"*10` and `truncate("one two three four", limit=9) == "one two ..."`.
3. Run the new file, then the full suite.
4. Open the draft PR. Do not merge.

## Risks

- Expected values were checked by reading the code, not run. By hand: tags become spaces, whitespace collapses, strip gives "Hello there"; `"one two three four"[:9]` is `"one two t"`, `rsplit(" ", 1)[0]` is `"one two"`, plus `" ..."`.
- If a test fails, report it. Do not alter the test or `normalize.py` to force a pass.
- Case 3 has two assertions in one test, so a failure on the first hides the second.
- The PR is meant to be closed unmerged. The standing merge authorization in CLAUDE.md must not be used here.

## Proof

- `python -m pytest tests/test_truncate_edges.py -q`: 3 passed.
- `python -m pytest -q`: whole suite passes.
- `git diff --stat main`: only `tests/test_truncate_edges.py` and files under `docs/intents/62-...`.
- Optional: change one expected value, see its test fail, then revert.

Tests come first: the plan is tests only, so there is no production code to write after them.

## Sizing (scrum master)

Small: one new file of about 20 lines, one reviewable PR, no split needed.

## Tasks

- [ ] Create `tests/test_truncate_edges.py` with the import
- [ ] Test 1: empty and `None` return `""`
- [ ] Test 2: tags stripped, whitespace collapsed
- [ ] Test 3: limit boundary unchanged, and word-boundary cut with `" ..."`
- [ ] Run the new file, then the full suite; report any failure without changing code or tests
- [ ] Check `git diff --stat main` shows only the allowed files
- [ ] Leave the PR as draft; do not merge
