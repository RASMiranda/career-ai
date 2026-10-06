---
name: add-profile
description: >
  Add a new person (profile) to the job scan, or add or update one of a
  profile's CVs. Use when asked to onboard a user, create a profile, set up
  someone's matching criteria, or add/rename/retire a CV variant.
---

# Add a profile (or a CV)

Everything personal goes in `career-data` (private). This repo is code only:
never copy a name, address, phone number or CV text into it.

The person must supply the facts. Ask for what is missing; never infer an email
address, contact detail, salary, rate or work-authorisation answer.

## New profile

1. **Id.** Lowercase, no spaces (`ana`). It is the folder name:
   `career-data/profiles/<id>/`.
2. **`profile.yaml`.** Copy `profiles/rui/profile.example.yaml` and fill it in:
   - `display_name`, `notify.email` (real address; placeholders and
     `example.com` are rejected by `validate`).
   - `languages`: BCP 47 tag -> CEFR level or basic/intermediate/professional/native
     (`pt-PT: native`). Ask the person; it drives the language prefilter (ADR-016).
   - `cv.dir` (their CV folder) and `cv.default` (a variant id that has a card).
   - `criteria` may be left out: it defaults to
     `profiles/<id>/01-knowledge/05-job-match.md`.
   - `weekly_day`, `pending_fit_floor`, `pending_limit`.
   - `daily_queries` / `weekly_queries`: only sources with `status: active` in
     `config.yaml → sources` (remotive, arbeitnow, adzuna, jsearch today). Start
     broad: the policy is broad collection, fine-grained elimination.
   - `applicant` and `answers`: leave the values empty unless the person gives
     them, and only needed for `apply run`. Never fill them from a CV.
   - Optional `blacklist:` (same shape as the global one) for this person only.
3. **`01-knowledge/05-job-match.md`.** The only document the scan reads. Write
   it *with* the person: target titles (`core`), adjacent titles (`radar`),
   engagement model, geography and mode, seniority, rate, sectors, signals of
   good alignment and **deal-breakers**. Mark any assumption "(default —
   adjust)". Use `profiles/rui/01-knowledge/05-job-match.md` for the shape only.
4. **Other knowledge documents** (`01-profile` … `04-direction`) are evidence for
   the human and for tailoring CVs; the scan does not read them. Create them
   only if asked.
5. **CV cards.** One per CV, see below.
6. **Check** (below), then commit in `career-data`.

## A CV variant

1. The CV lives in the person's CV folder (Drive layout: one subfolder per
   variant, free naming, PDF preferred over DOCX).
2. Run `python -m jobscan.cv --data ../career-data` to see the id derived from
   the folder name (person's name, shared prefix and "resume"/"cv" removed).
3. Write `profiles/<id>/cv/<variant>.md`, named exactly that id: front matter
   (`title`, `drive`, `updated`), then **Use for** (which roles), **Emphasis**
   (what this version foregrounds), and a "never use for ..." line where one
   applies (for example a sports CV). Describe the CV; do not paste its text,
   phone number or address.
4. Renaming or retiring a CV means renaming or deleting its card and updating
   `cv.default` if needed. A card with no file is fine in the cloud; a file with
   no card can never be chosen.

## Check

```bash
cd career-ai && export PYTHONPATH=src
python -m jobscan.cv --data ../career-data          # every variant has a card; default exists
python - <<'PY'
from pathlib import Path
from jobscan.config import load_config, recipient_problems
cfg = load_config(Path("../career-data"))
print([p["id"] for p in cfg["profiles"]], recipient_problems(cfg))   # expect []
PY
```

Then, if API keys are present, `collect` once and read its preflight lines
(`criteria[<id>]: ok`). Keys live in the routine's environment, not in files.

## Rules

- Do not edit `authorization.yaml` or `config.yaml` unless asked; a new profile
  needs neither.
- Each profile's email goes only to its own `notify.email`.
- Commit to `career-data`, never to this repo.
