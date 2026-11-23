# Plan: Throwaway docs-only note to exercise the SDLC stages

Spec: `spec.md` (issue #110). Intent: `intent.md`.

## Files that change (and why)

| File | Change | Why |
|---|---|---|
| `docs/intents/110-feature-open-one-small-throwaway-feature/throwaway-note.md` | new | The only feature (spec req. 1): a short plain-text note saying it is a rehearsal artifact for #110 and safe to delete. |
| `docs/intents/110-feature-open-one-small-throwaway-feature/plan.md` | this file | Plan-stage artifact (spec req. 3, 4). |

Nothing else. No code, test, workflow, hook, guard, profile, `career-data` or protected path (spec req. 3, 7).

## Order of work

1. Confirm the branch is `agent/110-…` and `git diff main --name-only` lists only this intent folder.
2. Write `throwaway-note.md`: two or three plain sentences. No personal data, link, credential or instruction to an agent (req. 2).
3. Run the proof checks below.
4. Stop. The PR is opened by the workflow; a human reviews and closes it unmerged (assumed) or merges.

## Risks

- **Feature undefined by the issue.** The docs-only note is the spec's assumption. If the owner wants a code or test change, the spec must be revised first and this plan redone.
- **Merge leaves a permanent throwaway file.** Mitigated by closing unmerged (spec open question 2); the owner decides.
- **Scope drift.** A path outside the intent folder, or any protected path, would fail the stage check. Keep the diff to the two files above.
- **Note wording read as an instruction.** Write it as a statement of fact, not an imperative addressed to an agent.

## Proof

No new test: the spec's non-goals exclude a test asserting the note's content, and none is added, removed or weakened.

1. `git diff main --name-only` lists only paths under `docs/intents/110-feature-open-one-small-throwaway-feature/` (reqs. 1, 3, 4, 6).
2. Read `throwaway-note.md`: it says it is a throwaway rehearsal artifact for #110, with no personal data, credential, URL or instruction (req. 2).
3. Compare the changed paths against the protected-path list: none appear (req. 3).
4. `python -m pytest -q` passes with the same tests as on `main` (req. 7).
5. On the issue, each of intent, spec, plan and build has a stage report, and each stage after intent started from an owner-applied label (reqs. 4, 5).

## Sizing (scrum master view)

One reviewable PR, a few lines of text in one new file. No split needed. I did not spawn the tech-lead or scrum-master subagents: with one file and no design choice, I wrote their parts directly.

## Tasks

- [ ] Confirm the diff against `main` touches only the intent folder
- [ ] Write `throwaway-note.md` (rehearsal artifact for #110, safe to delete; no personal data, link or instruction)
- [ ] Check the changed paths against the protected-path list
- [ ] Run `python -m pytest -q` and confirm it passes unchanged
- [ ] Leave merge or close to the owner
