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
  close, call GitHub or reach the web. `python -m sdlc_engine check` rejects anything outside the stage, any protected
  path (`.github/`, `.claude/`, `CLAUDE.md`, `REVIEW.md`, `routine-prompt.md`, `docs/DECISIONS.md`, dependency files,
  authorization, config and profiles, scripts, the `src/sdlc_engine/` package), and any credential, email or phone number in an added line. Only then does
  the workflow commit, push to `agent/*`, open the draft PR, start the tests and post the report. **No agent and no step of the
  privileged job runs the repository's tests** (ADR-037): see below.
- **Which code runs.** The steps that decide, skip, frame the issue and write the prompt run `sdlc_engine` from a second
  checkout of the trigger commit's `src/`, taken before any agent and again after each agent run, never from the issue's
  branch (ADR-036, ADR-058). The `src/sdlc_engine/` package is protected, so only a human PR can change the stage rules or
  the check. The workflow file itself takes effect only once it is merged to `main`.
- **Review.** Every build is followed by a reviewer and a security-reviewer pass (`REVIEW.md`), read only; apply
  `agent:review` to run them again after your own pushes. Findings never approve or block by themselves.
  The reviewers write `.sdlc/comment.md` too, so a trusted step copies the build agent's report to
  `.sdlc/build-report.md` before they start, and the build stage's post shows that copy first, then the review, the fixed
  tests line and the next gate (ADR-052).
- **Diagnostics (ADR-055).** When an agent is refused a tool, the issue comment says which, by name only, for example
  "Permission denials: stage agent 1 (Bash); reviewers 3 (Write, Read)". The tool's input is never shown. The job summary
  carries that line on every run, including "none". If the stage agent wrote no report, its final message follows,
  marked untrusted and shown only when the secrets and personal-data scan finds nothing in it.
- **Merge.** Only a human merges, after `pytest` is green and a code owner approves (branch protection). The agent that
  wrote the code never approves it. The draft PR body starts with `Closes #N`, so the PR shows in the issue's
  Development sidebar and merging it closes the issue (ADR-034): merge only after the checklist in the PR is done.

### Events that start nothing get their own concurrency group (ADR-039)
The issue forms apply `type:*` and `stage:intake` at creation, so one new issue fires `opened` plus one `labeled` per form
label within about a second. All of them used to share the group `sdlc-issue-N`; with `cancel-in-progress: false` a newer
*pending* run replaces an older pending one, so a no-op `labeled type:bug` could replace the real `opened` run (#50).
Now the group key and the job `if` use the same condition, which is `sdlc_engine.decide` written as an expression:

| Event | Starts a stage | Concurrency group | Job |
|---|---|---|---|
| `opened`, open and unlocked issue, author OWNER, MEMBER or COLLABORATOR | yes (`intent`, or `support-l1` for `type:support`) | `sdlc-issue-N` | runs |
| `labeled` with a key of `LABEL_TO_STAGE` (`agent:intent`, `spec`, `plan`, `build`, `review`, `release`, `support`, `l2`, `l3`), by a User, not a `[bot]` login | yes | `sdlc-issue-N` | runs |
| `labeled` with any other label (`type:*`, `stage:*`, `needs-info`, `support:*`) | no | `sdlc-noop-<run id>` | skipped |
| `opened` by anyone else; a bot or non-User label; closed or locked issue; a pull request | no | `sdlc-noop-<run id>` | skipped |

Two real events for the same issue still share `sdlc-issue-N` and queue as before. A no-op run still appears in the
Actions list (the trigger cannot filter by label) but finishes at once and takes no group a real run needs.
`decide` stays the authority inside the job; `tests/test_sdlc_concurrency.py` keeps the YAML condition equal to it.

### A stage whose output is already on the branch does not run (ADR-057)
`intent`, `spec` and `plan` each write one file (`intent.md`, `spec.md`, `plan.md`). When that file is already on the
checked-out branch, the run starts no agent, posts one line naming the file and how to redo the stage, and removes only
the trigger label. It adds no `stage:*` label and no next gate. To redo a stage, delete the file on the branch and apply
the label again. `build`, `review`, `release` and the support stages are never skipped. The check is trusted code
(`sdlc_engine skipped`), tested in `tests/test_sdlc_skip.py`.

### Label sets and concurrency (i.F4, ADR-039)
One agent label starts one stage. Two agent labels added together in the same second run one after the other, not as a
cancellation: they share the issue's group, and `cancel-in-progress` is false. GitHub keeps one pending run per group
and replaces an older pending run with a newer one, so with three or more queued events the middle one can be dropped;
that is documented GitHub behaviour and was not seen in a real run here. `needs-info`, `type:*`, `stage:*` and
`support:*` labels start nothing and never take the issue's group (`tests/test_sdlc_concurrency.py`).

### Workflow hygiene (i.F5)
- **Concurrency wording** (ADR-039 comment in `sdlc.yml`): checked against GitHub's replacement rule and left as written.
- **Checkout of the branch** now also waits for `stop`. Before, a budget stop still ran the checkout, which overwrote the
  budget message with "No branch for this issue yet" when no branch existed.
- **"The stage ended without a report from the agent."** now says to open the run log, where the agent's last message is
  shown when it could be read (ADR-055).
- **Next gate** is no longer printed on a stopped run (missing input, no branch, budget stop), so a reader is never told
  to apply the next label when nothing ran. A safety-check block already printed none.
- **Node 24:** `actions/checkout@v7` and `actions/setup-python@v7` (both run on Node 24, per their `action.yml` at the
  tag). The inputs used here are unchanged in those releases. Pinned by major tag, as before.
- **Runner image:** every workflow pins `runs-on: ubuntu-24.04`. GitHub's runner-images issue #14748 says `ubuntu-latest`
  moves to Ubuntu 26.04 with the migration to finish by 19 Nov 2026, and `ubuntu-24.04` stays available as a label.
  Python comes from `setup-python`, so the Python in use does not change with the image. Tools the workflows use
  (`git`, `gh`, `jq`, GNU `date`) are on the 24.04 image.

### Check `pytest` on agent PRs (i.F6, i.F7, no code change)
`sdlc.yml` dispatches `tests.yml` on the agent branch after the push. That run creates a check run named `pytest`
on the head commit (app `github-actions`). Read on 13 Nov 2026 for PRs #77 and #71: the dispatched run concluded
`success`, the `pull_request` run for the same SHA concluded `failure` with no jobs, and the check runs listed only the
dispatched `pytest`. The commit has no statuses. Ruleset `protect-main` (active) has no required status check.
The `pull_request` run can be ignored or cancelled; it creates no check. Not verified here: GitHub's docs on why the
bot-triggered run needs approval, and whether a required check is satisfied by a same-named check run from any event.
docs.github.com and github.blog did not resolve from this session. Before step k, check both in the docs and in a
throwaway chain. To make `pytest` required, a human adds a required status check named `pytest` to ruleset
`protect-main` (Settings, Rules, Rulesets, protect-main, Require status checks). Pin the source to the GitHub Actions
app only if the docs confirm the matching rule. No change to the fork-PR approval setting.

### Project values in one file (ADR-060)
The values the engine uses, such as the trusted author associations, the label-to-stage map, each stage's roles, outputs and turn limit, the protected paths, the size limits, the budget caps, the agent branch prefix and the model, live in `.github/sdlc-config.json`. The engine reads it with `--config` from the trigger commit (ADR-036), so a change takes effect only once a human merges it to main; it is a protected path, so no agent can write it. The built-in values in `src/sdlc_engine/` apply only when the file is absent, and a malformed file stops the run. `tests/test_sdlc_config_file.py` keeps the file equal to the built-in values and to the workflow text. The project's prompt text (the files a stage must never touch, the docs it reads first, the support sources, the bundle command), the owner's handle in the budget comment and the project's own credential shape are the optional `prompt` object and `budget.mention` of the same file (ADR-065): the built-in values are generic, and a second project supplies its own block in its own config. `tests/golden/` holds the rendered stage prompts and the blocked comment, compared byte for byte.

### A thin caller around the stage workflow (ADR-066)
`sdlc.yml` is the caller: it owns the name, the triggers, the concurrency group, the permissions each job is granted and the call. Its one job `stage` calls `sdlc-stage.yml`, a reusable workflow that holds every step and receives `CLAUDE_CODE_OAUTH_TOKEN` by name. The budget gate still counts the caller's runs. The steps are pinned byte for byte by `tests/golden/sdlc-steps.txt`. The job-level keys a caller may set, and how `github.*` resolves in a called workflow, are not yet checked against the GitHub docs (ADR-066).

### The review stage (ADR-067)
The reviewers answer in a fixed shape, parsed by the engine (`src/sdlc_engine/review.py`), not in free text. Line 1 is
`Nothing to fix.` or `N findings (I important, M nit, P pre-existing)`. Then one line per finding:
`IMPORTANT|NIT|PRE-EXISTING path:line - text`, with `line` a number or a range such as `10-20`. The review never gives a
verdict line; `IMPORTANT` findings are what block the next gate, and nothing else does.
- **Malformed fails closed.** A wrong first line, a count that disagrees with the findings, a line that is not a finding,
  more than 50 findings or a line over 300 characters makes the whole review one `IMPORTANT unparseable review`.
- **Drop rule.** An `IMPORTANT` or `NIT` whose line is not inside a hunk of `.sdlc/diff.patch` (changed lines and their
  context) is dropped, without a model call, and listed in the run summary by tag and line. `PRE-EXISTING` is not checked
  against the diff. A finding on a range is kept when any of its lines is in a hunk.
- **Checks line.** Always the first line of the check results read by a trusted step (ADR-037). On a successful read that
  line is `commit: <sha>`; the pass or fail of `pytest` is on the line after it. The reviewers may write files, so the post
  step never reads `.sdlc/checks.txt` back.
- **Risk tier** (on the draft PR body, from the changed paths and the protected paths in `.github/sdlc-config.json`, never
  from the author): HIGH when a protected path changed, LOW for docs and tests only, MEDIUM otherwise.
- **`needs_changes`** is true when a kept `IMPORTANT` finding exists. It only chooses the wording of the `Next gate` line.
  It ticks no box, adds no label and blocks nothing.

### The review round cap and the optional verifier (ADR-068)
Every pushed build is reviewed, so each review round costs usage. Two repository variables (Settings, Secrets and variables,
Actions, Variables) bound that:

| Repository variable | Meaning | Default |
|---|---|---|
| `SDLC_MAX_REVIEW_ROUNDS` | how many reviews may run on one issue | 3 |
| `SDLC_REVIEW_VERIFY` | set it to exactly `true` to turn the verifier on | off |

- **Round.** Each posted review carries a hidden marker, `<!-- sdlc-review round=N sha=… -->`. The round is one more than the
  markers in the issue's comments written by the workflow's own bot (`github-actions[bot]`). A marker from anyone else is
  ignored. A review runs while its round is at most the cap; with the default, rounds 1 to 3 run and round 4 is blocked.
  If the issue's comments cannot be read, the review is blocked too (fail closed).
- **Blocked round.** No review agent runs. The build's own report is still posted, followed by one short comment that starts
  with the owner's mention (`budget.mention` in `.github/sdlc-config.json`) and asks you to step back and reconsider the
  approach before another round. The job stays green and adds a warning annotation.
- **Diff only from round 3.** The review reads only the change since the commit in the latest marker, while that commit is
  still an ancestor of the branch. After a force-push or rebase it reads the full diff, and the run summary says so.
- **Verifier (off by default).** With `SDLC_REVIEW_VERIFY` set to exactly `true`, a second read-only agent (Read, Grep and
  Glob; 8 turns) checks each IMPORTANT finding against the code. Only a CONFIRMED finding is posted. A DROPPED finding is
  named in the run summary by tag and line only. A missing or malformed answer keeps every finding. It is off by default
  because it is one more model call on every review that has an IMPORTANT finding, and the owner's plan has usage limits.
- **To stop reviews entirely**, set `SDLC_MAX_REVIEW_ROUNDS` to `0`: every review is blocked, and the build still runs and
  posts its report. Remove the variable to go back to 3.

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

**Where `GH_TOKEN` lives (ADR-035).** It is set per step, never on the job: only "Budget gate", "Fetch the issue and PR comments (gh)", "Commit and push the artifact, open the draft PR, start the tests" and "Post the report, apply the stage label" carry it, because those call `gh` or `git push`. The agent steps and the safety `check` run without it and without `ANTHROPIC*` or `CLAUDE_CODE_OAUTH_TOKEN` variables (the OAuth token reaches only the action's `with:`). `anthropics/claude-code-action` writes the token into the `origin` URL in `.git/config` (`src/github/operations/git-config.ts`, `git remote set-url origin https://x-access-token:...`), so a step after each action run resets `origin` before any agent-written code runs. `tests/test_sdlc_token_scope.py` pins all of this by parsing the workflow. Not verified by a real run. ADR-036: the steps that import jobscan after an agent (check, push, review prompt, reject, post) run `python -P -m sdlc_engine` with `PYTHONPATH="$TRUSTED_SRC"`, a second `actions/checkout` of the trigger commit (`github.sha`, `path: trusted`, sparse `src`), fetched after each agent run, so code the agents wrote never runs in a step that holds the token. Git in those steps runs with hooks and fsmonitor off and ignores the global and system git config. The agents' own `Write` and `Edit` to `.git/` are refused by `scripts/hooks/guard.py`, and the reset steps strip anything else from `.git/config` and `.git/hooks`. That closes the gap for jobscan and for hooks and config. Still open: `.git/HEAD`, refs and objects are not reset, and the `claude` process environment still holds the token (the action sets it).

**Tests never run in the privileged job (ADR-037).** The `claude` process holds `GH_TOKEN`, `GITHUB_TOKEN` and the Claude GitHub App token, and job permissions do not limit the App token. A `conftest.py` or test the build agent wrote would run in that process, so the build stage no longer allows `Bash(python -m pytest:*)` (or pip, or any `python -m` of repo code), and the workflow has no dependency install and no "run the tests once more" step. Tests run only in `tests.yml` (read-only token, no secrets), dispatched by the push step with `gh workflow run tests.yml`. The build agent writes tests and does not run them; the build report carries a fixed line saying so, written by the workflow, not the agent: the `pytest` check on the PR is the evidence. If it is red, fix and re-apply `agent:build`. The review stage cannot run tests either: it reads `.sdlc/checks.txt`, which a workflow step (with `GH_TOKEN` on that step only) writes after the push for the commit just pushed, or before the agent for a `review` or `release` stage on the current HEAD, so the build agent cannot write it. First line `commit: <sha>`, then `name: status conclusion` per check run; if the call fails or returns nothing the file says `Could not read check results for <sha>: <reason>`. The Checks line of the review quotes the commit line (ADR-067), and the reviewers say "not known" when the check is queued, in_progress or unreadable (a review right after a build usually finds it unfinished), and claim passing tests only for a `pytest` check that is completed success. Whether the job token needs `checks: read` for this call is not verified: the first real run must show it (the repository is public). `Read(//proc/**)` is denied in `.claude/settings.json` and also passed as `--disallowedTools` to both agent steps, so a change to the checked-out settings cannot lift it; it covers the Read tool and file commands Claude Code recognises in Bash (`cat`, `head`), not a script that opens files itself, and Bash is limited by the allow-list. Still open: the `claude` process holds the tokens (the two-job split, a future ADR, is the remaining step).

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
