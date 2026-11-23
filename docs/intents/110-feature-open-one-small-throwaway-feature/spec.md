# Spec: Throwaway feature to exercise the SDLC stages end to end

Intent: `intent.md` (issue #110).

The issue names no feature. Per the intent's open question 1, this spec proposes the smallest harmless candidate: one docs-only note. The owner may override it when approving the spec.

## Requirements

1. The build stage adds exactly one new file, `docs/intents/110-feature-open-one-small-throwaway-feature/throwaway-note.md`, containing a short plain-text statement that it is a rehearsal artifact for issue #110 and is safe to delete.
2. The note holds no personal data, CV text, credential, URL to fetch or instruction to any agent.
3. Apart from the note, the build stage changes only SDLC bookkeeping inside `docs/intents/110-…/` (`plan.md`). It changes no code, test, workflow, hook, guard, profile or `career-data` file, and no protected path (`.github/**`, `.claude/**`, `CLAUDE.md`, `docs/DECISIONS.md`, `docs/SDLC.md`, `scripts/**`, `src/sdlc_engine/**`, `pyproject.toml`, `requirements*.txt`, `.gitignore`, and the other paths in the stage rules).
4. After the build, `docs/intents/110-…/` holds `intent.md`, `spec.md`, `plan.md` and the note: one artifact per stage, produced in that order.
5. Each hand-off between stages is a human applying the next `agent:*` label. No agent pushes, merges, labels or closes.
6. The build stage ends with a PR whose diff is limited to the files in 1 and 3, and which a human can close unmerged or revert without side effects.
7. `python -m pytest -q` passes unchanged. No test is added, removed or weakened.
8. No aiapply.co parity is claimed, as the issue gives no counterpart (ADR-017).

## Acceptance criteria

- **Given** the approved spec and plan, **when** the build stage finishes, **then** `git diff main --name-only` lists only files under `docs/intents/110-feature-open-one-small-throwaway-feature/`.
- **Given** the built branch, **when** `throwaway-note.md` is read, **then** it states that it is a throwaway rehearsal artifact for #110 and contains no personal data, credential, link or instruction.
- **Given** the built branch, **when** the diff is checked against the protected-path list, **then** no protected path appears.
- **Given** the built branch, **when** `python -m pytest -q` runs, **then** it passes with the same tests as on `main`.
- **Given** issue #110, **when** its comments and labels are read, **then** each of intent, spec, plan and build has a stage report, and each stage after intent started from a label applied by the owner.
- **Given** the owner decides to discard the work, **when** the PR is closed unmerged, **then** `main` is unchanged and nothing else needs reverting.

## Non-goals

- Any real product behaviour: scan, scoring, apply, profiles, reports, email, `career-data`.
- Any change to the SDLC engine, workflows, agents, hooks or guards, or any attempt to test them by weakening them.
- A test that asserts the note's content (it would be a guard on a throwaway file).
- aiapply.co parity work.
- Merging the PR. The assumption is that it is closed unmerged (intent, open question 2).

## Concerns flagged

No conflict with ADR-003, ADR-007 or ADR-017 to ADR-022, with a guardrail, or with a privacy or safety rule. The note is text-only, outside the protected paths, and adds no personal data.

For the owner to decide (not conflicts):

1. **What the throwaway feature is.** The issue gives none. This spec assumes a docs-only note placed inside the intent folder, so the stage-path checks stay trivially satisfied. If the owner wants a code or test change, the spec needs revising, and the plan must then avoid the protected paths.
2. **Merge or close.** If merged, a throwaway note stays in the repository permanently. Closing unmerged is assumed.
3. **Empty "done" and "Does aiapply.co do this?" fields.** Per ADR-017 this spec records "no counterpart claimed" and does not look for one.

## Test plan

No new automated test (see Non-goals). Verification:

1. Manual: `git diff main --name-only` shows only `docs/intents/110-…/` paths (Requirements 1, 3, 4, 6).
2. Manual: read the note for personal data, links or instructions (Requirement 2).
3. Manual: compare the changed paths against the protected-path list (Requirement 3).
4. Automated: `python -m pytest -q` passes unchanged (Requirement 7).
5. Manual: read the issue's stage comments and label history for the order and the human hand-offs (Requirements 4, 5).
