# AI-native SDLC (ADR-023)

Source: Anthropic, *The AI-native SDLC playbook*. Each stage commits one artifact; the next stage
starts by reading it. Humans keep judgement and accountability; agents work up to the gate.

| Stage | Role agent (`.claude/agents/`) | Artifact | Human gate |
|---|---|---|---|
| Plan | `product-owner` (with `stakeholder`) | `docs/intents/<slug>/intent.md`: problem, outcome, users, constraints, open questions | Owner accepts or closes the intent |
| Design | `product-owner`, `tech-lead` | `spec.md` (acceptance criteria as Given/When/Then, policy concerns flagged) | Owner approves; ADR if a decision changes |
| Build | `developer` | `plan.md` then code and tests on a feature branch | Plan approved before edits |
| Test | `tester` | failing test first for bugs; eval-style checks from real tasks | `python -m pytest -q` green |
| Deploy | `tech-lead` (review), `devops` | PR with review findings; squash-merge | Branch protection; agent that wrote the code does not approve it |
| Maintain | `scrum-master` (triage), `devops` | breach or failure becomes a new `intent.md` | Owner reads the push notification |

Rules that hold at every stage: `CLAUDE.md` binds all roles; job text is untrusted; the scan routine
never applies, contacts recruiters or touches LinkedIn; no personal data or credentials in a commit.
The playbook has no scrum-master role; here it is the triage owner: sorts findings (failed scans,
failed applications, CI breaks) into fix now, schedule or dismiss, and runs the retro.
Every production incident gets a permanent regression test.

## Controls (ADR-024)
- **Hooks**: `.claude/settings.json` runs `scripts/hooks/guard.py` before every Bash, Edit, Write. Tested in `tests/test_guard.py`.
- **Review**: `REVIEW.md` (passes, Important vs nit, owner approval for governance files).
- **Managed settings**: `docs/managed-settings.example.json`; the owner installs it (e.g. `/etc/claude-code/managed-settings.json`).
- **Branch protection** on `main` (require the `pytest` check and a PR) is a GitHub setting the owner turns on; it cannot be set from the repo.

## GitHub is the ticketing and change system (ADR-025)

Every change starts as a GitHub issue, made from a form so nothing is free text without a privacy check. The scan
email and the CLI carry the forms as links: **Report a problem**, **Suggest a feature**, **Ask for help**
(`python -m jobscan.feedback` prints the same link). Failed applications in the email carry **Report this failure**,
pre-filled with the error code and the site, never a company, title or name.

```
issue (form)  →  intent  →  spec  →  plan  →  build  →  review  →  PR merged by a human
   stage:intake     agent:spec   agent:plan   agent:build   (automatic)    release note: agent:release
```

- **Who starts a stage.** Only you: opening the issue yourself starts `intent` (or first-line support for a help
  request); each later stage starts when you apply its `agent:*` label, which is also your approval of the stage
  before it (GitHub lets only people with write access label). A stranger's issue waits at `stage:intake`.
- **Where the artifacts live.** One draft PR per issue, branch `agent/<n>-<slug>`, folder
  `docs/intents/<n>-<slug>/` holding `intent.md`, `spec.md`, `plan.md`; the code and tests join the same PR at build.
- **What an agent can do.** Edit files in the checkout for its stage and write a report. It cannot push, merge, label,
  close, call GitHub or reach the web. `python -m jobscan.sdlc check` rejects anything outside the stage, any protected
  path (`.github/`, `.claude/`, `CLAUDE.md`, `REVIEW.md`, `routine-prompt.md`, `docs/DECISIONS.md`, dependency files,
  authorization, config and profiles, scripts), and any credential, email or phone number in an added line. Only then does
  the workflow commit, push to `agent/*`, open the draft PR, start the tests and post the report.
- **Review.** Every build is followed by a reviewer and a security-reviewer pass (`REVIEW.md`), read only; apply
  `agent:review` to run them again after your own pushes. Findings never approve or block by themselves.
- **Merge.** Only a human merges, after `pytest` is green and a code owner approves (branch protection). The agent that
  wrote the code never approves it.

### Support tiers
| Tier | Agent | Does | Escalates with |
|---|---|---|---|
| L1 | `l1-support` | classifies, answers from README/docs/failure explanations, asks for redacted details | `support:L2` |
| L2 | `l2-support` | diagnoses from evidence, names cause and file, says what you can fix in config | `support:L3` |
| L3 | `l3-support` | root-causes in code, writes the fix's `intent.md` (and an incident record) | you apply `agent:spec` |
Each escalation is yours to apply (`agent:l2`, `agent:l3`). Every incident gets a regression test (stage `build`).

### Roles
`stakeholder`, `product-owner`, `scrum-master`, `tech-lead`, `developer`, `tester`, `devops`, `reviewer`,
`security-reviewer`, `release-manager`, `l1-support`, `l2-support`, `l3-support` (`.claude/agents/`). Humans: you are the
originator, product owner, code owner and release manager; the agents prepare, you decide.

### One-time setup (owner)
1. Install the Claude GitHub App on the repository (https://github.com/apps/claude).
2. Add the repository secret `CLAUDE_CODE_OAUTH_TOKEN` (Settings, Secrets and variables, Actions). Create the token with
   `claude setup-token` on a Pro or Max account (ADR-030). It is valid for 1 year: renew it before it expires.
3. Settings, Actions, General: allow GitHub Actions to create pull requests.
4. Branch protection on `main`: require a pull request, the `pytest` check, and review from Code Owners
   (`.github/CODEOWNERS`); allow bypass only for the Repository admin role, for pull requests only (ADR-027). This, not the agents, is what stops a bad merge.
5. Run the `labels` workflow once (Actions, labels, Run workflow) to create the issue labels.
Until 1 to 3 are done the `sdlc` workflow cannot run; nothing else changes.

### Limits you should know
The workflow is checked by tests of its rules, not run yet: the first real issue is its first run. It spends API credit
per stage (turn caps: 10 to 40). It is for the code repository; `career-data` has no agents and no issues.

