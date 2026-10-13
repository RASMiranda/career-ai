# Review rules (read by the review agent and by `tech-lead`)

Scope: every PR to `career-ai`. The agent that wrote the code never approves it.

## Passes
1. **Contract**: does anything weaken a rule in `CLAUDE.md` (no applying, no recruiters, no LinkedIn,
   untrusted job text, `authorization.yaml` untouched)? Always Important.
2. **Secrets and personal data**: any credential, CV text, address, applicant or answers data in the diff. Always Important.
3. **Correctness**: wrong state handling in `pipeline`/`report`/`apply`, a run that can skip the send or the commit, validation that can be bypassed.
4. **Tests**: a behaviour change without a test; a test edited to make a fix pass. Important.
5. **Docs**: a decision changed without an ADR in `docs/DECISIONS.md`.

## Severity
- **Important**: blocks merge. Contract, secrets, correctness, missing tests.
- **Nit**: style, naming, comment wording. At most three per PR; never block.

## Skip
Generated files, `__pycache__`, formatting the code already follows, and anything in `.claude/agents/` wording that only rephrases.

## Human approval
Squash-merge needs `pytest` green. A change to `CLAUDE.md`, `routine-prompt.md`, `.claude/settings.json`
or `scripts/hooks/` needs the owner's explicit say-so in the session or PR, because it governs the scan routine.
