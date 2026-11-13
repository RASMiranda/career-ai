# Intent: Throwaway: verify hygiene (i.F3-i.F7)

## Problem

Issue #79 is a throwaway. Its body only repeats the title. ADR-057 (workflow hygiene i.F3-i.F7) says workflow behaviour is verified only by tests until the throwaway chain runs, and it lists what that run must show. This issue is that run. There is no product need beyond that check.

## Proposed outcome

Running the intent stage on this issue, and then the later stages, shows the ADR-057 behaviours in a real run:

- An intent whose file is already on the branch posts only the skip line when `agent:intent` is applied again. It starts no agent and removes only the trigger label. It adds no `stage:*` label and names no next gate.
- A stopped spec run posts no "Next gate" line.
- The stage-ended message tells the reader to open the run log.
- The runs use the pinned `ubuntu-24.04` runner and the Node 24 `actions/checkout@v7` and `actions/setup-python@v7`.
- The `pytest` check on the agent PR is the dispatched run's check run (ADR-057 g).

Done means the owner has seen these and recorded the result. The recorded result should also cover the items ADR-057 lists as unverified. The issue does not say how to record it.

No change to the product or the scan.

## Affected users and systems

- The owner, who runs the throwaway chain.
- The `sdlc` workflow and its helper `jobscan.sdlc skipped`.
- No scan routine, profile, `career-data` or application submission involvement.

## Constraints

- ADR-057 (a to g), docs/SDLC.md "A stage whose output is already on the branch does not run", "Workflow hygiene (i.F5)" and "Check `pytest` on agent PRs (i.F6, i.F7)".
- ADR-025 and docs/SDLC.md: agents never merge, push to `main` or change protected paths (`.github/**` and `.claude/**` among them). This intent writes only its own file.
- CLAUDE.md: no personal data in `career-ai`. The issue states there is none.
- Out of scope: any code, workflow or ADR change. A fix for what the run reveals is a separate issue. Adding the required check is a repository setting and a human step (ADR-057 g).

## Open questions

- Where does the owner want the verification result recorded: the issue thread, or a new ADR consequence line? An agent cannot edit `docs/DECISIONS.md`.
- Should the throwaway issue and its PR be closed unmerged once checked? The issue is silent.
- "Does aiapply.co do this?" is blank. Nothing here is a product feature, so it is treated as not applicable (ADR-017).
