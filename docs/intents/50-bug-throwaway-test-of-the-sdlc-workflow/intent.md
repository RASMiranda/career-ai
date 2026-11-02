# Intent: Throwaway test of the sdlc workflow (#50)

## Problem

The owner wants to check that the sdlc workflow still works after PR #46: the intent stage should run once, push a draft PR and post a comment. The issue says nothing in the repository needs to change, and that it will be closed as not planned.

## Proposed outcome

- The intent stage runs once and produces this file and a short comment.
- No code, test, doc or configuration change follows from this issue.
- Done means the draft PR and the comment appear. The owner then closes the issue as not planned.

## Affected users and systems

- The owner, who is testing the workflow.
- The sdlc workflow (intent stage only). No product behaviour, job scan, profile or `career-data` is involved.

## Constraints

- Stop at the intent stage. Do not apply `agent:spec` (docs/SDLC.md).
- The issue body is untrusted input (CLAUDE.md, Security). Nothing in it asks for anything beyond this stage.
- The stage may write only this file and the comment and labels files. It touches no protected path and no personal data.
- No ADR conflict found. The ADRs the prompt lists were not re-read in full, because this test changes nothing.

## Open questions

- None for the product. The owner closes the issue as not planned after checking the draft PR and the comment.
- The issue is typed `bug` but describes no defect. Is that label only a template artefact of the test?

Out of scope: any implementation, spec, test or design work.

Note: the stakeholder and product-owner subagents were not run, because this throwaway has no scope to shape.
