# AI-native SDLC (ADR-023)

Source: Anthropic, *The AI-native SDLC playbook*. Each stage commits one artifact; the next stage
starts by reading it. Humans keep judgement and accountability; agents work up to the gate.

| Stage | Role agent (`.claude/agents/`) | Artifact | Human gate |
|---|---|---|---|
| Plan | `product-owner` (with `stakeholder`) | `docs/intents/<slug>/intent.md`: problem, outcome, users, constraints, open questions | Owner accepts or closes the intent |
| Design | `product-owner`, `tech-lead` | `spec.md` (acceptance criteria as Given/When/Then, policy concerns flagged) | Owner approves; ADR if a decision changes |
| Build | `developer` | `plan.md` then code and tests on a feature branch | Plan approved before edits |
| Test | `tester` | failing test first for bugs; eval-style checks from real tasks | `pytest` check green on the PR (`python -m pytest -q` locally) |
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
  the workflow commit, push to `agent/*`, open the draft PR, start the tests and post the report. **No agent and no step of the
  privileged job runs the repository's tests** (ADR-037): see below.
- **Review.** Every build is followed by a reviewer and a security-reviewer pass (`REVIEW.md`), read only; apply
  `agent:review` to run them again after your own pushes. Findings never approve or block by themselves.
- **Merge.** Only a human merges, after `pytest` is green and a code owner approves (branch protection). The agent that
  wrote the code never approves it. The draft PR body starts with `Closes #N`, so the PR shows in the issue's
  Development sidebar and merging it closes the issue (ADR-034): merge only after the checklist in the PR is done.

### Events that start nothing get their own concurrency group (ADR-039)
The issue forms apply `type:*` and `stage:intake` at creation, so one new issue fires `opened` plus one `labeled` per form
label within about a second. All of them used to share the group `sdlc-issue-N`; with `cancel-in-progress: false` a newer
*pending* run replaces an older pending one, so a no-op `labeled type:bug` could replace the real `opened` run (#50).
Now the group key and the job `if` use the same condition, which is `jobscan.sdlc.decide` written as an expression:

| Event | Starts a stage | Concurrency group | Job |
|---|---|---|---|
| `opened`, open and unlocked issue, author OWNER, MEMBER or COLLABORATOR | yes (`intent`, or `support-l1` for `type:support`) | `sdlc-issue-N` | runs |
| `labeled` with a key of `LABEL_TO_STAGE` (`agent:intent`, `spec`, `plan`, `build`, `review`, `release`, `support`, `l2`, `l3`), by a User, not a `[bot]` login | yes | `sdlc-issue-N` | runs |
| `labeled` with any other label (`type:*`, `stage:*`, `needs-info`, `support:*`) | no | `sdlc-noop-<run id>` | skipped |
| `opened` by anyone else; a bot or non-User label; closed or locked issue; a pull request | no | `sdlc-noop-<run id>` | skipped |

Two real events for the same issue still share `sdlc-issue-N` and queue as before. A no-op run still appears in the
Actions list (the trigger cannot filter by label) but finishes at once and takes no group a real run needs.
`decide` stays the authority inside the job; `tests/test_sdlc_concurrency.py` keeps the YAML condition equal to it.

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

### Token rotation and revocation
- **Rotate:** mint a new token with `claude setup-token` (re-running it does not replace the old one). Update the
  `CLAUDE_CODE_OAUTH_TOKEN` secret and the Bitwarden entry, then revoke the old token in
  claude.ai → Settings → Claude Code → Authorization tokens (verified 2026-10-23), then verify that the workflow still authenticates and the old token no longer works.
- **If leaked:** delete the repository secret first, then revoke the token, verify the revocation, check usage for spikes,
  and contact Anthropic support if the token still works.

CLAUDE_CODE_OAUTH_TOKEN was created 2026-10-23 and expires 2027-10-23. The expiry date is recorded in the repository variable CLAUDE_TOKEN_EXPIRES (a plain-text date, not a secret). When you rotate the token, update that variable too.

The subprocess env scrub (`CLAUDE_CODE_SUBPROCESS_ENV_SCRUB`) is not used: it needs bubblewrap and failed the first run (ADR-033). Since ADR-035 the repository token is no longer in that environment (see below).

**Where `GH_TOKEN` lives (ADR-035).** It is set per step, never on the job: only "Budget gate", "Fetch the issue and PR comments (gh)", "Commit and push the artifact, open the draft PR, start the tests" and "Post the report, apply the stage label" carry it, because those call `gh` or `git push`. The agent steps and the safety `check` run without it and without `ANTHROPIC*` or `CLAUDE_CODE_OAUTH_TOKEN` variables (the OAuth token reaches only the action's `with:`). `anthropics/claude-code-action` writes the token into the `origin` URL in `.git/config` (`src/github/operations/git-config.ts`, `git remote set-url origin https://x-access-token:...`), so a step after each action run resets `origin` before any agent-written code runs. `tests/test_sdlc_token_scope.py` pins all of this by parsing the workflow. Not verified by a real run. ADR-036: the steps that import jobscan after an agent (check, push, review prompt, reject, post) run `python -P -m jobscan.sdlc` with `PYTHONPATH="$TRUSTED_SRC"`, a second `actions/checkout` of the trigger commit (`github.sha`, `path: trusted`, sparse `src`), fetched after each agent run, so code the agents wrote never runs in a step that holds the token. Git in those steps runs with hooks and fsmonitor off and ignores the global and system git config. The agents' own `Write` and `Edit` to `.git/` are refused by `scripts/hooks/guard.py`, and the reset steps strip anything else from `.git/config` and `.git/hooks`. That closes the gap for jobscan and for hooks and config. Still open: `.git/HEAD`, refs and objects are not reset, and the `claude` process environment still holds the token (the action sets it).

**Tests never run in the privileged job (ADR-037).** The `claude` process holds `GH_TOKEN`, `GITHUB_TOKEN` and the Claude GitHub App token, and job permissions do not limit the App token. A `conftest.py` or test the build agent wrote would run in that process, so the build stage no longer allows `Bash(python -m pytest:*)` (or pip, or any `python -m` of repo code), and the workflow has no dependency install and no "run the tests once more" step. Tests run only in `tests.yml` (read-only token, no secrets), dispatched by the push step with `gh workflow run tests.yml`. The build agent writes tests and does not run them; the build report carries a fixed line saying so, written by the workflow, not the agent: the `pytest` check on the PR is the evidence. If it is red, fix and re-apply `agent:build`. The review stage cannot run tests either: it reads `.sdlc/checks.txt`, which a workflow step (with `GH_TOKEN` on that step only) writes after the push for the commit just pushed, or before the agent for a `review` or `release` stage on the current HEAD, so the build agent cannot write it. First line `commit: <sha>`, then `name: status conclusion` per check run; if the call fails or returns nothing the file says `Could not read check results for <sha>: <reason>`. The reviewers quote the commit line, say "not known" when the check is queued, in_progress or unreadable (a review right after a build usually finds it unfinished), and claim passing tests only for a `pytest` check that is completed success. Whether the job token needs `checks: read` for this call is not verified: the first real run must show it (the repository is public). `Read(//proc/**)` is denied in `.claude/settings.json` and also passed as `--disallowedTools` to both agent steps, so a change to the checked-out settings cannot lift it; it covers the Read tool and file commands Claude Code recognises in Bash (`cat`, `head`), not a script that opens files itself, and Bash is limited by the allow-list. Still open: the `claude` process holds the tokens (the two-job split, a future ADR, is the remaining step).

**The agent cannot read the checkout's `.git` (ADR-051).** Before the agent starts, `claude-code-action` writes its token into `remote.origin.url` in `.git/config`, and a bare `Read`, `Grep` or `Glob` could read it. `Read(**/.git/**)` is denied in `.claude/settings.json` and in `--disallowedTools` on both agent steps (a later stage checks out the issue branch, so the flag is the rule that always applies), and `permissions.blockReadsOutsideWorkingDirectories` keeps the file tools inside the checkout. Checked with a before/after probe and a fake token: before, Read, Grep and Glob all read `.git/config`; after, Read and Grep are denied, Glob returns nothing, a read of `/etc/hostname` is denied and a read of `README.md` still works. Not closed by this: the OAuth token stays in the `claude` process, and a deny rule is a pattern match, not a sandbox. The agent/publish job split (i.H7 in the setup guide) stays optional and is deferred to before multi-user use.

### Limits you should know
The workflow is checked by tests of its rules, not run yet: the first real issue is its first run. It spends API credit
per stage (turn caps: 10 to 40). It is for the code repository; `career-data` has no agents and no issues.

## Usage budget

The agents run on the owner's Pro subscription (ADR-030), so a hard cap on agent time protects the usage limits.
The "Budget gate" step (ADR-032) adds up the minutes of earlier `sdlc` runs (duration is `updated_at - run_started_at`,
an approximation; runs under 30 seconds, cancelled runs and the current run do not count) and refuses the stage when
either window is over its cap. It comments on the issue, stays green, and the step summary of every run shows the
minutes used, the caps and the decision.

| Repository variable (Settings, Secrets and variables, Actions, Variables) | Window | Default |
|---|---|---|
| `SDLC_MAX_AGENT_MIN_24H` | rolling 24 hours | 60 |
| `SDLC_MAX_AGENT_MIN_7D` | rolling 7 days | 240 |

Unset or non-numeric means the default, never unlimited. Exactly at a cap is allowed. **To stop everything**, set
either variable to `0`: every stage is refused until you raise it. Remove the variable to go back to the default.
