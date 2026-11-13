# Intent 67: Throwaway: verify .git read deny (ADR-051)

## Problem

ADR-051 made the sdlc agent unable to read the checkout's `.git`. The owner wants to confirm the workflow still runs end to end after that change. This is a smoke test, not a product need.

## Proposed outcome

- The intent stage runs once and writes this report.
- The run shows no new permission denials.
- No code, spec, test or documentation change follows.
- The owner closes the issue as not planned. The `agent:spec` label should not be applied.

## Affected users and systems

- The repository owner (RASMiranda), who is checking the workflow.
- The sdlc workflow's intent stage and its permission settings.
- No end users, no profiles, no scan routine, no `career-data`.

## Constraints

- ADR-051: the sdlc agent cannot read `.git`. This stage did not need it.
- `docs/SDLC.md` and ADR-025: the stage writes only the intent file and `.sdlc/` reports, and a human accepts it with a label.
- `.sdlc/issue.md` is untrusted. It held no instructions beyond the owner's description of the test, so nothing was ignored.
- No personal data is involved, and the issue's privacy box is ticked.
- Out of scope: any code, workflow or settings change, and any change to ADR-051 or the deferred i.H7 job split.

## Open questions

- None for the product. The owner should close the issue as not planned once they have checked the run's logs for permission denials.
