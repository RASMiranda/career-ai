# Intent 75: Throwaway: verify denial notes (ADR-055)

## Problem

The owner wants to confirm that the `sdlc` workflow still runs end to end after ADR-055
(denied tools are named, and the agent's last message is shown when it wrote no report).
The issue is a throwaway test, not a product need. It asks for no code change.

## Proposed outcome

The intent stage runs once and writes this intent report. Nothing else is built.
The owner then closes the issue as not planned.

## Affected users and systems

- The owner, who reads the stage output to judge the workflow.
- The `sdlc` workflow, intent stage only.
- No product code, scan routine, profile or `career-data` is affected.

## Constraints

- No code, test, guard or rule change is wanted (CLAUDE.md, development sessions).
- The issue text is untrusted input; this report works from it and obeys nothing in it.
- The stage writes only this file plus `.sdlc/comment.md`.
- Scope is not checked against ADR-017 (aiapply.co parity); the issue answers "n/a".

## Open questions

- None for the product. The owner should close the issue as not planned instead of applying `agent:spec`.
- Note: the role agents (stakeholder, product-owner) were not spawned, because the request has no product content to shape.
