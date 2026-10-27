# Intent 37: Fix typo in README ("recieve" → "receive")

## Problem

The owner reports that the README contains the misspelling "recieve" and wants it spelled "receive". The issue gives no file, line or branch. A case-insensitive search of this checkout (outside `.sdlc/`) finds no "recieve" anywhere, in `README.md` or any other file. The typo may already be fixed, or it may be a different spelling or on another branch.

## Proposed outcome

Done means no misspelling of "receive" remains in the README. If the typo is already gone, done means the issue is closed with no code change.

Out of scope: a wider spell-check or copy edit of the docs, any rewording, and any change outside the README.

## Affected users and systems

- The owner and any reader of `README.md`.
- No scan, scoring, application or profile behaviour is affected. No personal data is involved.

## Constraints

- CLAUDE.md: the change touches documentation only. No personal data in a commit, and no change to protected paths.
- No ADR (003, 007, 017–022) is touched. I did not re-read them in full because this is a text-only fix, so a conflict is unlikely but unchecked.
- The stakeholder and product-owner subagents were not run. The intent is small enough to write directly.

## Open questions

- Where did you see the typo (file, line, branch)? Or is it a different word?
- If the typo is gone, should this issue be closed instead of moving to `agent:spec`?
