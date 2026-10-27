# Plan: Fix typo in README ("seperate" → "separate")

Spec: `spec.md` (issue #44).

## Files that change (and why)

- `README.md`, line 6: "seperate" → "separate". The only product change.
- `docs/intents/44-…/` bookkeeping only (this plan, ticked tasks). No other file.

No code, test, config, profile or protected path is touched.

## Order of work

1. Confirm the typo is still at `README.md` line 6.
2. Make the one-word edit.
3. Run the proof checks below.
4. Open one PR; squash-merge after `python -m pytest -q` passes.

## Size (scrum master view)

One reviewable PR, a one-word diff. No split needed.

## Risks

- Editing more than the word (whitespace, line endings). Mitigation: check the diff is one line.
- The grep in the spec matches the quoted old spelling in `.sdlc/` and `docs/intents/44-…/`; those hits are expected and are not to be edited.
- No ADR conflict, no personal data, no guard affected.

## Proof

No new automated test. A test on one word's spelling is the spell-check guard the intent rules out (spec, Test plan).

1. `git diff main -- README.md` shows exactly one changed line, differing only by `e`→`a` (Req. 1, 2).
2. `grep -rn "seperate" --include=*.md . | grep -v -e '^./.sdlc/' -e '^./docs/intents/44-'` prints nothing (Req. 3).
3. `git diff --stat main` lists only `README.md` plus files under `docs/intents/44-…/` (Req. 4).
4. `python -m pytest -q` passes (Req. 5).

## Tasks

- [ ] Confirm "seperate" is at `README.md` line 6
- [ ] Change it to "separate", touching nothing else
- [ ] Run proof checks 1–3
- [ ] Run `python -m pytest -q`, confirm it passes
- [ ] Open the PR; note the proof results in its description
