# Intent: Fix typo in README ("seperate" → "separate")

## Problem

`README.md` line 6 reads "live in a seperate **private** repository". "seperate" is a misspelling of "separate". It is the only occurrence in the repository's Markdown files. Reported by the owner (issue #44).

## Proposed outcome

The word on `README.md` line 6 reads "separate". Nothing else in the README changes. Done means a search for "seperate" in the repo's Markdown files finds nothing.

## Affected users and systems

- Readers of `README.md` (owner, contributors).
- No code, pipeline, scan routine, profile or `career-data` involvement.

## Constraints

- No personal data in the change (CLAUDE.md: `career-ai` is code only).
- Text-only edit. It touches no ADR (ADR-003, ADR-007, ADR-017 to ADR-022) and no protected path (`README.md` is not on the protected list).
- Out of scope: any other wording, formatting or documentation edits, and a spell-checker or CI check.

## Open questions

None.
