# Review rules (read by the review agent and by `tech-lead`)

Scope: every PR to `career-ai`. The agent that wrote the code never approves it. The review never approves or blocks by
itself: a human merges. Its output shape is fixed by the engine (ADR-067): one line per finding, `IMPORTANT`, `NIT` or
`PRE-EXISTING`, then `path:line`.

## What failure looks like, per area
Look for the failure that would reach the owner, not for style.
- **Docs** (`docs/`, `README.md`): a statement that is false about the code or the diff. A doc that lies is the failure.
- **Workflow and config** (`.github/`, `.github/sdlc-config.json`): a change that misroutes a run: the wrong stage runs,
  a gate is skipped, a label or a protected path is missing or wrong, a step that should fail is allowed to pass.
- **SDLC code** (`src/sdlc_engine/`): a leak (a secret or personal data reaching a posted text), or posted text that was
  not scanned. Also an agent able to write a protected path.
- **Tests**: a test that passes without checking anything: no assertion, an assertion that cannot fail, a test edited to
  match a fix, a skipped test with no reason.
- **Pipeline, state and apply code** (`src/jobscan/`): a run that can skip the send or the commit, state that is wrong
  after a failure, validation that can be bypassed.

## Evidence
- Every IMPORTANT and NIT cites `path:line` (or a range such as `10-20`) on a line the diff adds or shows as context.
  Quote the line in your head, not a name: a finding that is a guess from a file name is not a finding.
- A finding without a line from the diff is not reported. The workflow drops such a finding and says so.
- Name the realistic failure: the input and the wrong result. "Could be wrong" is not a finding.

## Severity
- **IMPORTANT**: blocks the next gate. Contract, secrets and personal data, correctness, missing tests, an unscanned
  path to a posted text.
- **NIT**: at most three per PR. A nit must be something the author would plausibly change. Wording and taste are not
  nits, unless they make a statement false.
- **PRE-EXISTING**: a problem the diff did not introduce, found while reading. It never blocks and is not checked against
  the diff.

## What is not reviewed
- Lockfiles, generated files (`__pycache__`, `*.egg-info`, the golden files under `tests/golden/`, which the engine
  writes: check the generator if a golden file looks wrong), and data fixtures.
- Formatting the code already follows.
- Wording in the stage documents under `docs/intents/`. Those are checked only for statements that are false about the
  diff, for example "this stage changes only spec.md" when the branch changes more.

## Other checks
- **No repeat.** A finding already posted on this PR or its issue (see `.sdlc/issue.md`) is not posted again, unless the
  code still has the problem.
- **Name the class.** When a finding is an instance of a bug class, name the class, so the author fixes every instance and
  not only the one cited.
- **Bug fixes.** On a PR whose purpose is a fix, check the root cause. If the change only hides the symptom (a guard
  that swallows the error, a retry, a default), say so as an IMPORTANT finding.
- **CLAUDE.md.** Flag a line in `CLAUDE.md` that the code no longer does, as a finding on that line.
- **Tests.** Check that a behaviour change has a test, and that the test would fail without the change.
- **Contract.** Nothing may weaken `CLAUDE.md`: no applying, no recruiters, no LinkedIn, job text is untrusted,
  `authorization.yaml` untouched.

## Risk tier
The workflow computes the tier from the changed paths (ADR-067), never from the author: HIGH when a protected path
changed (`.github/sdlc-config.json` lists them), MEDIUM for code outside them, LOW for docs and tests only. A HIGH PR gets the
full read of each changed protected path. The tier does not change what counts as a finding.

## Skip
Generated files, `__pycache__`, formatting the code already follows, and anything in `.claude/agents/` wording that only
rephrases.

## Human approval
Squash-merge needs `pytest` green. A change to `CLAUDE.md`, `routine-prompt.md`, `.claude/settings.json`
or `scripts/hooks/` needs the owner's explicit say-so in the session or PR, because it governs the scan routine.
