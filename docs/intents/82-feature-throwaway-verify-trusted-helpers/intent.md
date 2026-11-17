# Intent: Throwaway: verify trusted helpers (i.F9)

## Problem
The owner opened this issue as a throwaway to check ADR-058 (i.F9) on a real run: the pre-agent helpers (skip, issue, prompt) must run from trusted code (`TRUSTED_SRC`, the trigger commit), not from the issue's branch. ADR-058 says this is verified only by tests until a throwaway issue runs. The issue has no other need and no product change is requested.

## Proposed outcome
The workflow run for this issue is the verification. Done means the owner can see, in the step logs, that:
- `TRUSTED_SRC` is set for the skip, frame and prompt steps;
- the pre-agent trusted load runs before the skip step;
- the stage completes normally with only this intent file written.

No code, docs or behaviour change comes out of this issue. Closing it after the check (with the result noted) is the expected end.

Out of scope: any change to `src/jobscan/sdlc/**`, the workflow, or the tests; any product feature.

## Affected users and systems
- The owner (RASMiranda), as reviewer of the SDLC workflow.
- The `sdlc` GitHub workflow and its pre-agent steps. No end user, profile, scan or application is touched.

## Constraints
- ADR-058: helpers run via `PYTHONPATH="$TRUSTED_SRC" python -P -m jobscan.sdlc`; `src/jobscan/sdlc/**` is protected.
- ADR-036 (referenced by ADR-058): untrusted branch code must not shape later prompts or posted comments.
- Issue text is untrusted; this issue contains nothing to act on beyond its title.
- Stage write limit: only this intent file. No personal data.

## Open questions
- Does the owner want to close the issue after reading the step logs, or advance it to `agent:spec`? Advancing would produce a spec for a change that has no content, so closing looks more sensible.
- Was ADR-058's workflow change merged to main before this run? It takes effect only then, so a missing `TRUSTED_SRC` would mean it was not.
