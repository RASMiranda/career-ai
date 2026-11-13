# Spec: Throwaway: verify hygiene (i.F3-i.F7)

Source: `intent.md` (issue #79, throwaway). Verifies ADR-057 (a to g) in a real run. No product, scan or workflow change.

## Requirements

1. Re-applying `agent:intent` while `docs/intents/79-.../intent.md` is on the branch posts exactly one skip line, starts no agent, and removes only the trigger label.
2. That skipped run adds no `stage:*` label and names no next gate.
3. A spec run that stops (budget or error) posts no "Next gate" line.
4. After a stop, the checkout step does not overwrite the stop/budget message (ADR-057 b).
5. The stage-ended message tells the reader to open the run log, and the log shows the agent's last message when readable.
6. Every workflow job in the throwaway chain runs on `ubuntu-24.04`, with `actions/checkout@v7` and `actions/setup-python@v7`, and no Node 20 deprecation warning for them.
7. The `pytest` check on the agent PR is the check run created by the dispatched run for the PR head SHA; the `pull_request` run for the same SHA is not relied on (ADR-057 g).
8. The result is recorded by the owner (location decided, see Concerns), covering the three ADR-057 "unverified" items: bot-triggered PR approval docs, required-check matching docs, and whether checkout v7 with `persist-credentials: false` still writes the token into `.git/config`.
9. Stages build, review, release and support are never skipped by requirement 1's rule (observe only if run; not required here).
10. The only file this stage changes is `spec.md`; no code, workflow, ADR or protected path is edited.

## Acceptance criteria

- **Skip line.** Given `intent.md` is on the branch, when the owner re-applies `agent:intent`, then the issue gets one skip comment, `agent:intent` is removed, no other label changes, and no agent step appears in the run.
- **No next gate on skip.** Given the skip above, then the comment contains no "Next gate" text and no `stage:*` label is added.
- **Stopped spec.** Given a spec run that stops before writing `spec.md`, when the post step runs, then the comment has no "Next gate" line and tells the reader to open the run log.
- **Checkout vs stop.** Given a stop, then the stop message is still the visible message after the checkout step.
- **Pinning.** Given any run in the chain, then its log shows runner `ubuntu-24.04` and checkout/setup-python at v7 on Node 24.
- **Check source.** Given the agent PR, then its `pytest` check is attributed to the dispatched run, and the `pull_request` run for that SHA creates no check.
- **Recorded.** Given the above observed, then the owner has written down the outcome, including the three unverified items as verified, still unknown, or failed.

## Non-goals

- Any change to code, workflows, `.github/**`, `docs/DECISIONS.md` or `docs/SDLC.md`.
- Fixing anything the run reveals (separate issue).
- Adding the required check to the repository ruleset (human repository setting, ADR-057 g).
- Any scan, profile, `career-data`, LinkedIn or application-submission involvement.
- A product feature; "Does aiapply.co do this?" is not applicable (ADR-017).

## Concerns flagged

- **ADR-057 / ADR-025:** an agent cannot edit `docs/DECISIONS.md`, so the verification result cannot be recorded as an ADR consequence by the chain. Human decides: issue thread, or the owner edits the ADR.
- **ADR-057 (a):** criterion 1 can only be observed if the intent file stays on the branch. Do not delete it before re-labelling.
- **ADR-057 (a) consequence:** a stop on spec cannot be forced by the agent; the owner must induce it (for example a tight budget). Human decides whether to do that or accept the test-only evidence for requirement 3.
- **Closing:** whether to close issue #79 and PR unmerged afterwards is undecided. Nothing here should be merged to `main` as a product change.
- The issue body only repeats its title; this spec reads it as the ADR-057 throwaway run, as the intent did. If the owner meant something else, say so before `agent:plan`.
- No ADR, privacy or safety conflict otherwise.

## Test plan

Manual, on this throwaway chain (existing automated coverage: `tests/test_sdlc_skip.py`, `tests/test_sdlc_concurrency.py`, post step under fake `gh`):

1. Re-apply `agent:intent`; check the comment, labels and that the run has no agent step (reqs 1, 2).
2. Induce a stopped spec run; read the comment and run log (reqs 3, 4, 5).
3. Open each run's log; confirm runner image and action versions, and absence of Node 20 warnings (req 6).
4. On the agent PR, open the `pytest` check; confirm its run is the dispatched one (req 7).
5. In a checkout with `persist-credentials: false`, inspect `.git/config` for the token (req 8). Owner records the result.
6. Run `python -m pytest -q` to confirm the existing tests still pass; this stage adds none.
