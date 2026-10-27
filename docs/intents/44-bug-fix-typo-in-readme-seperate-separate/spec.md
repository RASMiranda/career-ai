# Spec: Fix typo in README ("seperate" → "separate")

Intent: `intent.md` (issue #44).

## Requirements

1. `README.md` line 6 reads "live in a separate **private**" instead of "live in a seperate **private**".
2. No other byte of `README.md` changes (one word, one line in the diff).
3. After the change, `grep -rniw "seperate" --include=*.md .` finds no match outside `.sdlc/` (which holds the issue text) and this `docs/intents/44-…/` folder, where the old spelling is quoted.
4. No file other than `README.md` is changed by the build stage (apart from SDLC bookkeeping under `docs/intents/44-…/`).
5. `python -m pytest -q` still passes.

## Acceptance criteria

- **Given** `README.md` at the current head, **when** the fix is applied, **then** line 6 reads
  `search queries, run state and generated reports live in a separate **private**`.
- **Given** the fixed branch, **when** `git diff main -- README.md` is read, **then** it shows exactly one changed line, differing only by `e`→`a` in that word.
- **Given** the fixed branch, **when** the Markdown files outside `.sdlc/` and `docs/intents/` are searched for "seperate", **then** there is no match.
- **Given** the fixed branch, **when** `python -m pytest -q` runs, **then** it passes.

## Non-goals

- Any other wording, formatting or documentation edit.
- A spell-checker, linter or CI guard for typos.
- Any code, pipeline, profile, scan-routine or `career-data` change.
- Editing `intent.md` quoting of the old spelling.

## Concerns flagged

None. The change is a text-only edit to `README.md`, which is not a protected path. It touches no ADR (ADR-003, ADR-007, ADR-017 to ADR-022), no guardrail and no privacy or safety rule, and adds no personal data.

## Test plan

No new automated test: a test asserting one word's spelling in the README would be a spell-check guard, which the intent rules out. Verification:

1. Manual: `git diff main -- README.md` shows the single-line change (Requirements 1–2).
2. Manual: `grep -rn "seperate" --include=*.md .` shows hits only in `.sdlc/` and `docs/intents/44-…/` (Requirement 3).
3. Automated: `python -m pytest -q` passes unchanged (Requirement 5).
