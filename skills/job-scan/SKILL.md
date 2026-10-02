---
name: job-scan
description: >
  Run or debug the daily job scan. Use when asked to run a scan, re-score
  candidates, adjust matching criteria, or investigate why a run sent nothing.
---

# Job scan

The functional contract is in `CLAUDE.md` at the repo root. Read it first.

## Common tasks

**Re-score without re-collecting.** Reuse the existing `/tmp/candidates.json`
and rewrite `/tmp/decisions.json`. Collection costs API quota; scoring does not.

**A run sent nothing.** In order: was `authorization.active` true? Did
`collect` report source errors? Were all candidates already in
`state/job-scan-seen.json`? Did `validate` exit non-zero? Each prints its own
reason.

**Too much noise.** Fix `05-job-match.md`, not the prompt. Add the
deal-breaker that should have caught the false positive, then re-score the same
candidates file and compare.

**Too little.** Check whether queries are over-narrow before adding sources.
The policy is broad collection, fine-grained elimination.

## Monthly review

Report: new opportunities seen, duplicates suppressed, matches emailed, items
explored by the human, main discard reasons, best-signal sources, criteria that
need changing. Propose edits to `05-job-match.md` as a diff; do not apply them
silently.

## Applications

**An auto-apply failed.** Run `python -m jobscan.apply bundle`, read the
grouped failures, and propose the smallest adapter change plus a pytest case
built from the `form_outline`. Hard constraints: never solve or bypass a
CAPTCHA, never auto-answer legal/consent/work-authorisation questions, never
invent applicant data. "Hand to the human" is a valid fix.

**Something was submitted that should not have been.** Stop. Set
`application_submission.allow_auto_submit: false`, then read
`applications/queue.json` and `logs/apply/` to see which rule let it through
and add a test that fails on it before fixing it.
