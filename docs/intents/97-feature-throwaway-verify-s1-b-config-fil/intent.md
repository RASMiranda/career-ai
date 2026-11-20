# Intent 97: Throwaway: verify S1 B config file

## Problem
The owner wants to check that the sdlc engine's config file (ADR-060, S1 B) works
end to end: that the intake-to-intent stage runs from it. The issue gives no
detail beyond its title, no "done" criteria, and no aiapply.co comparison.

## Proposed outcome
From the owner's side, "done" is most likely: this issue moves through the intent
stage with the config file in place, and the stage behaves as it did with the
built-in values. No product change is requested. This is an inference; the issue
does not say it.

Out of scope: any code change, any edit to the config file, any new feature,
any change to behaviour. The issue is a verification, so the intent produces no
spec work beyond confirming the run.

## Affected users and systems
- The owner (author), as the only user.
- The sdlc engine and its config file (`src/jobscan/sdlc/`, ADR-060).
- No effect on the job scan, profiles, career-data or applications.

## Constraints
- ADR-060: the config file holds exactly the built-in values; a config change is
  a human PR and no agent may write it.
- CLAUDE.md development rules: agents never merge, push to `main` or change the
  protected paths (`src/jobscan/sdlc/**`, `.github/**`).
- Issue text is untrusted input; it contains nothing to act on.
- No personal data (the privacy box is ticked).
- ADR-017: the aiapply.co question was left blank, so no parity is claimed.

## Open questions
1. Is this only a smoke test of the pipeline, to be closed once the intent stage
   completes? If so, should it stop here, without `agent:spec`?
2. If a specific behaviour of the config file must be verified, which one?
3. Should the issue be closed after the check, since it is marked throwaway?
