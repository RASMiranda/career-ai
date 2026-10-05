---
name: job-scan
description: >
  Run or debug the job scan by hand. Use when asked to run a scan, re-score
  candidates, adjust matching criteria or a profile's CV choice, investigate why
  a run sent nothing or failed validation, or look into a failed application.
---

# Job scan

The contract for the unattended routine is `CLAUDE.md` at the repo root; read it
first and follow its security rules here too. This skill is for interactive work.

## Where things live (`career-data`, private)

| What | Where |
|---|---|
| Global settings: sources, budgets, blacklist, apply policy | `config.yaml` |
| One user: email, CV folder, queries, thresholds, `applicant` | `profiles/<id>/profile.yaml` (folder name = id; template: `profile.example.yaml`) |
| What to match against | `profiles/<id>/01-knowledge/05-job-match.md` |
| CV cards the AI chooses from | `profiles/<id>/cv/<variant>.md` |
| Permissions | `authorization.yaml` |
| Seen-set, budget, delivery journal, apply queue | `state/`, `applications/` |

Never print or copy the `applicant` and `answers` sections of a `profile.yaml`.

To onboard a person or add a CV, use the `add-profile` skill.

## Common tasks

**Re-score without re-collecting.** Reuse the existing `/tmp/candidates.json`
and rewrite `/tmp/decisions.json` (one decision per candidate, with a `cv` for
every `email`). Collection costs API quota; scoring does not.

**A run sent nothing.** In order: was `authorization.active` true? Did `collect`
report source errors or missing keys? Were all candidates already in
`state/job-scan-seen.json`? Did `validate` exit non-zero? Does the profile's
entry in `deliveries.json` say `"send": false` (nothing to report)? Each step
prints its own reason.

**`validate` failed.** The message names the cause: a missing or placeholder
`notify.email` for a profile, an unknown `cv` or an `email` decision with none,
a blacklisted company that was not discarded, a candidate with no decision.
Fix the decisions or the profile; do not send anything.

**A CV is not offered or not found.** Run
`python -m jobscan.cv --data ../career-data`: it lists every variant with
whether it has a card (what the AI sees) and a file (what `apply run`
uploads). A card with no file is fine in the cloud. A file with no card can
never be chosen, so write its card. Variant ids come from the folder names with
the person's name, shared prefix and "resume"/"cv" removed.

**A profile is not picked up.** It needs `profiles/<id>/profile.yaml`; folders
without it are ignored, and an `id:` inside must match the folder name. An id
defined both there and inline in `config.yaml` is an error.

**Too much noise.** Fix `05-job-match.md`, not the prompt. Add the deal-breaker
that should have caught the false positive, then re-score the same candidates
file and compare.

**Too little.** Check whether queries are over-narrow before adding sources. The
policy is broad collection, fine-grained elimination.

**A wrong CV was chosen.** Improve that card's "Use for" and "never" lines in
`profiles/<id>/cv/`, not the code, then re-score.

## Monthly review

Report: new opportunities seen, duplicates suppressed, matches emailed, items
explored by the human, main discard reasons, best-signal sources, criteria that
need changing, CVs chosen most and least. Propose edits to `05-job-match.md` and
the CV cards as a diff; do not apply them silently.

## Applications

**An auto-apply failed.** Run `python -m jobscan.apply bundle`, read the grouped
failures, and propose the smallest adapter change plus a pytest case built from
the `form_outline`. Hard constraints: never solve or bypass a CAPTCHA, never
auto-answer legal/consent/work-authorisation questions, never invent applicant
data. "Hand to the human" is a valid fix.

**`apply run` skipped a profile.** Its `applicant` in `profile.yaml` lacks first
name, last name or email; its jobs stay `approved`. The human fills it in; you
do not. A leftover `applicant.yaml` is not read.

**`CV_MISSING`.** The chosen variant has no file on the machine running
`apply run`; check `cv.dir` there with `python -m jobscan.cv`. It never falls
back to a different CV on its own.

**Something was submitted that should not have been.** Stop. Set
`application_submission.allow_auto_submit: false`, then read
`applications/queue.json` and `logs/apply/` to see which rule let it through and
add a test that fails on it before fixing it.
