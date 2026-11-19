# Intent 87: Throwaway chain to verify the required `pytest` check on an agent PR (i.F7)

## Problem
The owner wants to make `pytest` a required status check on ruleset `protect-main`, but two things are unverified
(docs/SDLC.md, "Check `pytest` on agent PRs (i.F6, i.F7)"): whether a required check is satisfied by the same-named check
run that `sdlc.yml` dispatches on the agent branch, and why the bot-triggered `pull_request` run ends `failure` with no
jobs. The issue text only repeats its title, so the need is inferred from that SDLC section.

## Proposed outcome
Stakeholder view: the owner can see, on a real agent PR from a disposable chain, whether a required `pytest` check
passes and lets the PR merge, and gets a clear yes or no to decide on enabling it. Done means one observed result
recorded for the owner: the check appears on the head commit, its state, and whether the merge button honours it.

Product owner scope: this is a verification chain only. It produces evidence, not a feature. The intent-stage output is this
file; later stages should add no product behaviour.

Out of scope: changing `tests.yml`, `sdlc.yml` or the ruleset, the fork-PR approval setting, and any change to scan or
apply behaviour.

## Affected users and systems
- The owner (decides on the ruleset change; a human edits ruleset `protect-main`).
- `sdlc.yml` and `tests.yml` workflows, and the agent PR flow.
- No effect on the job scan, profiles or `career-data`.

## Constraints
- Agents never merge, push to `main` or change protected paths (CLAUDE.md "Development sessions", docs/SDLC.md).
- Do not weaken a test, hook or guard to get a green check.
- No personal data or credentials in the chain (privacy box is ticked).
- The throwaway PR should be closed or discarded after the observation. This does not touch ADR-017 to ADR-022
  (scan, apply and reference-product rules), so no ADR conflict found.
- Making the check required is a human action in repository settings, not an agent action.

## Open questions
1. Is the goal only to observe the check state, or also to test that a failing `pytest` blocks merge?
2. Should the throwaway PR be closed unmerged, or may the owner merge it (it carries no code change)?
3. Should the result be written back into docs/SDLC.md (a protected path for agents, so a human or a separate issue)?
4. Pin the required check to the GitHub Actions app only if the docs confirm the matching rule; who confirms that?
