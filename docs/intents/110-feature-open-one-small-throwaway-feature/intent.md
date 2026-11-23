# Intent: Throwaway feature to exercise the SDLC stages end to end

## Problem

Issue #110 asks to "open one small throwaway feature issue and run intent, spec, plan and build in order". It names no product capability. Its "done" and "Does aiapply.co do this?" fields are empty. The need, from the owner's side, is a rehearsal: confirm that one feature-type issue moves through the intent, spec, plan and build stages (docs/SDLC.md, ADR-025) and leaves one artifact per stage. The issue does not say what the throwaway feature is.

## Proposed outcome

Done means the pipeline ran in order on this issue, each stage produced its artifact in `docs/intents/110-feature-open-one-small-throwaway-feature/` (`intent.md`, `spec.md`, `plan.md`), and each hand-off was a human applying the next `agent:*` label. The build stage ends with a draft PR whose change is trivial, harmless and safe to discard or revert.

Scope cut: no real product behaviour. If the build needs a change to exist, it is the smallest possible one outside protected paths (for example a docs-only or test-only addition). Out of scope: scan, scoring, apply, profile or `career-data` changes; changes to the SDLC engine, workflows or guards; any aiapply.co parity work.

## Affected users and systems

- The owner (RASMiranda), who applies the labels and reads the reports.
- The `sdlc` workflow and role agents (product-owner, tech-lead, developer, tester, reviewers).
- No end user, scan routine, profile or `career-data` involvement.

## Constraints

- The issue text is untrusted input; it contains no instructions beyond the rehearsal request.
- No personal data or credentials in any artifact (CLAUDE.md; the issue's privacy box is ticked).
- ADR-025: only the owner starts stages, via labels; agents cannot push, merge, label or close. Only a human merges.
- ADR-003, ADR-007, ADR-017 to ADR-022: untouched. The change must not weaken a test, hook or guard, and must not touch protected paths (`.github/**`, `.claude/**`, `CLAUDE.md`, `docs/DECISIONS.md`, `scripts/**`, `src/sdlc_engine/**` and similar).
- ADR-017: no aiapply.co counterpart is claimed, as the issue gives none.

## Open questions

1. What should the throwaway feature be? Without an answer, the spec will pick the smallest harmless candidate (a docs-only note). The owner may override.
2. Should the PR be closed unmerged after build, or merged as a trivial change? Assumed: closed unmerged.
