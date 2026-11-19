# Intent: Throwaway: verify i.F8 (no tests-green box)

## Problem
The owner wants to confirm that ADR-059 (i.F8) works end to end: a draft PR body made by the SDLC flow no longer has a `tests green` checkbox. The issue gives no behaviour change beyond that. Its "what do you need" and "what would done look like" both repeat the title.

## Proposed outcome
- This issue runs through the SDLC stages as a smoke test.
- The resulting draft PR body lists the four remaining boxes (intent accepted, spec approved, plan approved, review findings resolved) and has no `tests green` box.
- The required `pytest` check is the only automatic test gate.
- Done: the owner sees the PR body and the check, then closes the issue and the PR without merging.

Out of scope: any code, docs or workflow change, a new gate, and anything beyond what ADR-059 already decided.

## Affected users and systems
- The owner (RASMiranda), who reads the PR body.
- The `jobscan.sdlc` PR body builder and the SDLC workflow, observed only.
- No scan, profile, application or personal data is involved.

## Constraints
- ADR-059: the tests-green box is removed and the required `pytest` check replaces it.
- ADR-057: agent PRs need one approval click per run before the check reports.
- ADR-025 and `docs/SDLC.md`: agents never merge or push to `main`, and the protected paths stay untouched.
- `CLAUDE.md`: no personal data in the repo, and no weakening of a guard or test.
- `.sdlc/issue.md` is untrusted input and was treated as data.

## Open questions
- Is this a pure verification run with no code change? The intent assumes yes. If a change is wanted, the owner should say what it is.
- Should the throwaway PR and branch be closed unmerged afterwards? The intent assumes yes.
