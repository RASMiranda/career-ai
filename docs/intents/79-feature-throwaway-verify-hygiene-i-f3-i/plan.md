# Plan: Throwaway: verify hygiene (i.F3-i.F7)

Source: `spec.md` (issue #79). Verifies ADR-057 (a to g) in a real run. No product, scan or workflow change.

## Size (scrum master)

One reviewable PR, and a tiny one. The build stage changes no code. Its only deliverable is a short verification
record in this directory (`verification.md`) written from what the owner observes. Do not split. Do not merge to
`main` as a product change: the owner decides whether to close issue #79 and PR #80 unmerged afterwards.

## Files that change (and why)

- `docs/intents/79-feature-throwaway-verify-hygiene-i-f3-i/verification.md` (new): a checklist of the spec's
  acceptance criteria with observed / not observed / failed, plus the three ADR-057 "unverified" items. It exists
  because an agent cannot edit `docs/DECISIONS.md` (ADR-025), so the result lives beside the intent until the owner
  copies it to an ADR or the issue thread.
- Nothing else. No code, test, workflow, `.github/**`, `docs/DECISIONS.md`, `docs/SDLC.md` or protected path.

## Order of work

1. Run `python -m pytest -q` first on the branch to get a baseline (spec test plan step 6). Existing coverage is
   `tests/test_sdlc_skip.py`, `tests/test_sdlc_concurrency.py` and the post step under a fake `gh`. No new test is
   written: the spec adds no behaviour.
2. Keep `intent.md` on the branch. Owner re-applies `agent:intent`; check reqs 1 and 2.
3. Owner induces a stopped spec run (for example a tight budget) and reads the comment and log; reqs 3, 4, 5. If the
   owner declines, the record says "test-only evidence" for req 3.
4. Owner opens the logs of each run in the chain; req 6 (runner `ubuntu-24.04`, checkout and setup-python v7, no
   Node 20 warning).
5. On the agent PR, owner checks the `pytest` check's run is the dispatched one and the `pull_request` run made no
   check; req 7.
6. Owner inspects `.git/config` in a checkout with `persist-credentials: false`; req 8. Owner also notes the GitHub
   docs for bot-triggered PR approval and required-check matching, if they now resolve.
7. Developer writes `verification.md` from the owner's observations. Do not fill in a result nobody observed.

## Risks

- The issue body only repeats its title. This plan keeps the intent's and spec's reading (the ADR-057 throwaway
  run). If the owner meant something else, say so before `agent:build`.
- Req 1 can only be observed while `intent.md` is on the branch; deleting it first would run the stage again.
- A stopped spec cannot be forced by an agent; it needs the owner (budget or error).
- Observations of workflow runs need GitHub, which agents do not have. The developer cannot verify reqs 1 to 7
  alone; recording a guess would be false evidence.
- A run that shows ADR-057 behaving wrongly is a finding for a separate issue, not fixed here (non-goal).
- Required check in the repository ruleset is a human setting (ADR-057 g); not done here.

## Proof

- `python -m pytest -q` passes, before and after (no new tests; this stage adds no behaviour).
- `git diff --name-only main...HEAD` lists only files under `docs/intents/79-feature-throwaway-verify-hygiene-i-f3-i/`.
- Per spec criterion, the owner's observation: skip line (one comment, `agent:intent` removed, no other label, no
  agent step); no "Next gate" on skip; stopped spec has no "Next gate" and points to the run log; stop message
  survives checkout; runner and actions pinned on Node 24; `pytest` check attributed to the dispatched run.
- `verification.md` has one line per criterion and per unverified item, each marked verified, still unknown or failed.

## Tasks

- [ ] Run `python -m pytest -q` and note the result.
- [ ] Confirm `intent.md` is still on the branch.
- [ ] Owner: re-apply `agent:intent`; record skip comment, labels, no agent step (reqs 1, 2).
- [ ] Owner: induce a stopped spec run, or record "test-only evidence" (reqs 3, 4, 5).
- [ ] Owner: record runner image, action versions and Node warnings from the run logs (req 6).
- [ ] Owner: record the source of the `pytest` check on the PR (req 7).
- [ ] Owner: record `.git/config` token result for checkout v7 with `persist-credentials: false`, and the two docs items (req 8).
- [ ] Write `verification.md` with only what was observed.
- [ ] Check the diff touches only this directory.
- [ ] Owner decides where the result is recorded, and whether to close issue #79 and PR #80 unmerged.
