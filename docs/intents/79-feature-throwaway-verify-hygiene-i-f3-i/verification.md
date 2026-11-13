# Verification: ADR-057 hygiene (issue #79, throwaway)

Source: `spec.md`, `plan.md`. Nothing here was observed by the build agent: it has no access to GitHub runs. Each line
is **still unknown** until the owner fills in what they saw. Allowed marks: verified, still unknown, failed.

| # | Criterion | Mark | Observation (owner) |
|---|-----------|------|---------------------|
| 1 | Re-applied `agent:intent` posts one skip line, no agent step, only trigger label removed | still unknown | |
| 2 | Skipped run adds no `stage:*` label and has no "Next gate" text | still unknown | |
| 3 | Stopped spec run posts no "Next gate" line (or: test-only evidence accepted) | still unknown | |
| 4 | Checkout does not overwrite the stop/budget message | still unknown | |
| 5 | Stage-ended message points to the run log; log shows the agent's last message when readable | still unknown | |
| 6 | Runner `ubuntu-24.04`, `actions/checkout@v7`, `actions/setup-python@v7`, no Node 20 warning | still unknown | |
| 7 | `pytest` check on the agent PR comes from the dispatched run, not the `pull_request` run | still unknown | |
| 8 | Result recorded by the owner | still unknown | |

## ADR-057 "unverified" items

| Item | Mark | Observation (owner) |
|------|------|---------------------|
| GitHub docs: bot-triggered PR approval | still unknown | |
| GitHub docs: required-check matching | still unknown | |
| Checkout v7 with `persist-credentials: false` still writes the token into `.git/config` | still unknown | |

## Open decisions (owner)

- Where the final result is recorded (an agent cannot edit `docs/DECISIONS.md`).
- Whether to induce a stopped spec run or accept test-only evidence for criterion 3.
- Whether to close issue #79 and PR #80 unmerged afterwards.
