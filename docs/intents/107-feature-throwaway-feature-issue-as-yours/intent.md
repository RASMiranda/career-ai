# Intent: Throwaway feature issue (S2 test)

## Problem

Issue #107 (owner) reads "throwaway feature issue as yourself, with a short title and body S2". It names no feature, no user need and no behaviour. "Done", the aiapply.co question and the context are all empty. It looks like a throwaway issue used to exercise the SDLC workflow (the S2 workflow split, #106), not a product request.

## Proposed outcome

No product change. Done means the intent stage ran end to end on this issue and produced this file. The owner closes the issue, or supplies a real need and re-runs the stage.

## Affected users and systems

- The owner, as the person testing the `sdlc` workflow.
- No scan routine, pipeline, profile, `career-data` or application code involvement.

## Constraints

- No personal data in the change (CLAUDE.md: `career-ai` is code only).
- Writes only to this intent file. The protected paths stay untouched (`.github/**`, `.claude/**`, `src/sdlc_engine/**`, and the rest of the list).
- No ADR conflict (ADR-003, ADR-007, ADR-017 to ADR-022 not touched). The reference-product rule (ADR-017) has nothing to apply to without a feature.
- Out of scope: any code, doc or workflow change, and inventing a feature from the title.

## Open questions

- Is this issue purely a workflow test? If so, close it rather than applying `agent:spec`.
- If a real feature is meant, what is it, and what does "done" look like?
