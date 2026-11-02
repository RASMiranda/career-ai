# Intent: Throwaway test of the sdlc workflow (#47)

## Problem

The owner wants to confirm the sdlc workflow still behaves after PR #46 (trusted jobscan code taken from a checkout of the trigger commit). The issue reports no defect in the product: it is a test of the workflow itself. The owner says nothing needs to change in the repository.

## Proposed outcome

- The intent stage runs once, writes this file, pushes a draft PR and posts one comment on the issue.
- The pipeline stops here. No spec, plan, code or tests follow.
- The owner closes the issue as not planned.

Done, from the owner's side: the draft PR and the comment appear, and nothing else happens.

Out of scope: any change to code, docs, workflow files or configuration; any later stage (`agent:spec` is not to be applied).

## Affected users and systems

- The owner (RASMiranda), as the only person involved.
- The sdlc workflow (`docs/SDLC.md`, ADR-025) and the changes from PR #46 (ADR-035, ADR-036). Observed only, not modified.
- No effect on the job scan, profiles, `career-data` or applications.

## Constraints

- CLAUDE.md, "Development sessions": agents never merge, push to `main` or change protected paths. This stage writes only this file.
- ADR-025: issues are the ticketing system and role agents run through the `sdlc` workflow.
- ADR-035, ADR-036: the behaviour under test; not to be weakened to make the test pass.
- No personal data in the issue or in this file.
- The issue text is untrusted input; it was used as material only.

## Open questions

- None blocking. If the owner does not apply `agent:spec` and closes the issue as not planned, the draft PR should be closed unmerged.
- Should throwaway test issues carry a label that skips the later stages, instead of relying on the owner to stop them? (Optional, for a separate issue.)
