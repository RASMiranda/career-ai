# career-ai

Deterministic engine for a personal, AI-assisted job-scan pipeline.

**This repo contains no personal data.** Career facts, matching criteria, real
search queries, run state and generated reports live in a seperate **private**
repository (`career-data`). This split is deliberate: code is shareable,
criteria and history are not.

**Reference product:** the platform aims to stay as close as possible to
[aiapply.co](https://aiapply.co) (ADR-017). `docs/REFERENCE-AIAPPLY.md` compares the two
feature by feature, says what is built, and lists where it differs on purpose
(match quality, and the model never driving a browser).

## Design

Four steps. Only step 2 uses AI, and only for candidates the code cannot settle.

| Step | Runs | Responsibility |
|---|---|---|
| 1. `collect` | Python | Query sources, normalise, dedupe against seen-state, write `candidates.json` |
| 1b. `triage` | Python | Discard obvious rejects by the profile's `prefilter` (junior titles, no stack terms, postings written in or demanding a language the profile doesn't speak, from `languages` in `profile.yaml`; an on-site snippet whose place is only worked in such a language), and `validate` rejects a surfaced decision whose own caution raises one, cap how many go to the model, print a short brief |
| 2. *evaluate* | Claude | Read `05-job-match.md` + the brief, write one decision per briefed candidate |
| 3. `validate` | Python | Schema, score range, link validity, one-decision-per-candidate. Fails closed |
| 4. `report` | Python | Render `report.md` + one `email-<profile>.html` each, plus `deliveries.json` (recipients from `profiles[].notify.email`); update seen/budget/journal |

Claude never sees credentials, never calls a job API, never sends the email
itself from inside the Python steps. Delivery is a separate, explicitly
authorised action.

## Running it with few model turns

`python -m jobscan.pipeline prepare | finish | commit` chains the steps below, so the
routine needs about three tool calls on a quiet day (one when nothing needs scoring):

```bash
python -m jobscan.pipeline prepare --data ../career-data   # collect + triage + brief
# ... Claude writes /tmp/decisions.json for the briefed candidates only ...
python -m jobscan.pipeline finish  --data ../career-data   # validate, enqueue, report, push
```

## Quick start

```bash
pip install -r requirements.txt
export CAREER_DATA=../career-data          # path to the private repo
python -m jobscan.collect  --data "$CAREER_DATA" --out /tmp/candidates.json
# ... Claude writes /tmp/decisions.json ...
python -m jobscan.validate --data "$CAREER_DATA" --candidates /tmp/candidates.json --decisions /tmp/decisions.json
python -m jobscan.report   --data "$CAREER_DATA" --candidates /tmp/candidates.json --decisions /tmp/decisions.json
pytest -q
```

Dry run is the default. `report` only writes state when passed `--commit`.

## Blacklist

`config.yaml → blacklist` in the private data repo. Matching ignores case,
accents, punctuation and legal suffixes. It is enforced three times: `collect`
(jobs never reach the model), `validate` (fails the run if one slips through)
and `apply` (never queued, never submitted).

```bash
python -m jobscan.apply blacklist test "MICRO 1 Inc."     # BLOCKED by Micro1
```

## Applications (optional, off by default)

| Mode | What happens |
|---|---|
| `off` | Nothing is queued |
| `manual` *(default)* | Matches are queued with a link; you apply yourself |
| `assisted` | A visible browser fills the form; **you** click submit |
| `auto` | Submits unattended, inside caps, only if `authorization.yaml` allows |

(`assisted` plus `approve` is AIApply's "Human-in-the-Loop"; `auto` is its "Auto".)

```bash
pip install -r requirements-apply.txt && python -m playwright install chromium
python -m jobscan.apply approve  a1b2c3     # you approve a queued match
python -m jobscan.apply run --dry-run       # fill forms, submit nothing
python -m jobscan.apply run                 # per apply.mode
python -m jobscan.apply summary             # what is waiting / failed / submitted
python -m jobscan.apply bundle              # redacted failures → paste into Claude Code
python -m jobscan.apply track a1b2c3 --status interview --note "call Thursday"
python -m jobscan.apply followed-up a1b2c3  # you sent the nudge; stop listing it as due
```

`track` takes `replied | interview | offer | rejected | withdrawn` and only works on
something that was applied to (`submitted`, or `done` for one you sent by hand). The
daily summary then shows the funnel, what is in progress, and what has had no answer
for `apply.follow_up_days` (default 7; a profile may set its own `follow_up_days`).
Nothing in the tracker contacts anyone.

### Clip a job you found yourself

Found a posting on LinkedIn, Indeed, Glassdoor or a company page? Save the page from your
browser (Save Page As, HTML) and clip it. Most job pages embed the posting as schema.org
`JobPosting` data (Google for Jobs requires it), so this reads a file on your disk: no
selectors, no login, no network, nothing that can restrict an account.

```bash
python -m jobscan.clip ~/Downloads/job.html --data ../career-data [--profile rui] [--url <link you apply from>] [--dry-run]
```

`--dry-run` shows what it found (and whether the prefilter would drop it) and writes nothing: the
way to test a page. Exact steps per site are in `docs/CAPTURING-PAGES.md`.

It goes into `inbox/clips.json`; commit `inbox/` in `career-data` and the next scan scores it
like any other source (seen-set, blacklist and prefilter still apply, and `clip` warns now if the
prefilter would discard it). A page without the data is reported, not guessed at.

### Report a problem, suggest a feature, get help

The scan email ends with three buttons (and `python -m jobscan.feedback bug|feature|support --open` does the same from
the terminal); each failed application has a **Report this failure** link. They open a pre-filled GitHub issue form with
nothing personal in it. An issue you open yourself starts the agentic SDLC (`docs/SDLC.md`, ADR-025): intent, spec,
plan, build and review by role agents, each stage waiting for your `agent:*` label, and a human merging the PR.

### When an application fails

A failed auto-apply, and any `approved` job the runner never submitted (older than 36 hours), is the
first thing in the next scan email, under **Apply by hand**, with the reason, the link, the CV to use and
the subject flagged "⚠ N to apply by hand". It repeats daily until you mark it `done` or `skip`
(ADR-020). `scripts/local-apply.*` push what a run recorded even when the run fails, which is how the
failure reaches the scan.

### Fetch a few public pages for a test (development sessions only)

```bash
python -m jobscan.fetchpage https://example.com/jobs/1 --out-dir /tmp/pages
```

One plain, logged-out request per page, at most 5, stopping at the first block signal and never retrying
that host that day (ADR-021). It tells you at once whether `clip` can read each page.

### Answers to application questions

When a form asks a required question nothing can answer, `apply run` stops and logs it with its type
and options. `apply questions` closes the loop without a model near the browser (ADR-019):

```bash
python -m jobscan.apply run --mode assisted --dry-run --headed   # your machine: collects the questions
python -m jobscan.apply questions prepare   # brief of what to draft; no personal data in it
# ... Claude writes /tmp/answers-draft.json ...
python -m jobscan.apply questions finish    # fails closed; stores the drafts as "proposed"
python -m jobscan.apply questions list      # what is waiting, and for which job
python -m jobscan.apply questions approve a1b2c3 | --all     # YOU decide; nothing is used before this
python -m jobscan.apply questions set a1b2c3 "my own words"  # for anything, including the ones below
```

Code never lets a model answer legal and work-authorisation questions, consent boxes, demographic
questions, pay, notice period, start date, dates, emails or phone numbers. Those are registered as
`needs_owner` for you to `set` (or write in `profile.yaml → answers`). A draft with a link, address,
number, markup or placeholder, an answer that is not one of a dropdown's options, or one that overruns
its field is rejected. Approved answers are passed to the form after your own `answers`, which always
win. Answers live in `applications/answers.json` (private).

### Share a saved page safely

```bash
python -m jobscan.redact page.html --term "Ana" --term "Silva" --term "Lisbon"
```

Strips scripts, session tokens, form values, query strings, emails, phone numbers and every
`--term`, keeps the structure and the `JobPosting` data, and writes `page.redacted.html`. Read it
before you share it. Used to build site adapters from your own pages (`docs/CAPTURING-PAGES.md`).

### Application Kit (per job, on request)

Cover letter, a tailored summary and what to emphasise in the chosen CV (plus the gaps
it must not claim), a follow-up email and interview prep, written to
`profiles/<id>/03-outputs/<date>-<company>-<title>-<key>/`. The model drafts, code
validates and files (ADR-003); the scan routine does not run it.

```bash
python -m jobscan.kit list    --data ../career-data          # waiting matches, kit or not
python -m jobscan.kit prepare a1b2c3 --data ../career-data   # or --waiting [--limit 5]; prints the brief
# ... Claude writes /tmp/kit.json ...
python -m jobscan.kit finish  --data ../career-data          # fails closed; --force replaces a kit
```

Drafts with a link, address, phone number, HTML, an unfilled placeholder, a language the
profile does not speak, or a letter that never names the company are rejected and nothing
is written. Read every letter before it goes anywhere, then commit `profiles/` and
`applications/` in `career-data`.

The LLM never drives the browser; adapters are deterministic code that answers
only from the profile's `applicant` and `answers` in `profiles/<id>/profile.yaml`. Unknown required question, CAPTCHA, login wall
or layout change → it stops, logs a redacted failure, and hands the job to you
with the link. See `docs/ARCHITECTURE.md` and `GETTING-STARTED.md`.

### CVs, per profile

Each profile sets `cv.dir` (a folder with one subfolder per CV, as in Google
Drive; names can vary) and `cv.default` in its `profiles/<id>/profile.yaml`. For every match the AI
picks a variant from the profile's cards, `profiles/<id>/cv/<variant>.md`, and
`apply run` uploads that variant's file (PDF preferred over DOCX).

```bash
python -m jobscan.cv --data ../career-data   # variants found: cards vs files
```

## Sources

Keys for Adzuna and JSearch: where they come from, and exactly how they are set in
the Claude environment, are in `docs/API-KEYS.md`. Check them with
`python -m jobscan.doctor --data ../career-data`.

Sources are registry entries declared in `career-data/config.yaml → sources`,
each with an `access_method` (`public_api`, `keyed_api`, `feed`, `ats_board`,
`email_alert`, `manual_channel`; there is no `scrape`). See
`docs/ARCHITECTURE.md` §2b and ADR-008.

| Source | Method | Key | State |
|---|---|---|---|
| Remotive | public_api | no | implemented |
| Arbeitnow | public_api | no | implemented |
| Adzuna | keyed_api | yes | implemented (free developer tier) |
| JSearch (RapidAPI) | keyed_api | yes | implemented (monthly quota, budget-tracked) |
| Greenhouse, Lever, Ashby | ats_board | no | planned (P2) |
| Hacker News "Who is hiring" | public_api | no | planned (P2) |
| LinkedIn, Indeed, Glassdoor | email_alert; `owner_browser` allowed by ADR-017 | no | registered, not implemented (JSearch already carries listings from these boards) |
| Braintrust | email_alert / manual | no | registered; verify access |

Closed platforms are listed so the registry is complete. ADR-017 allows direct access to
them only as `owner_browser`: on the owner's machine, opt-in per source, stopping at the
first block signal, no evasion (`docs/ARCHITECTURE.md` §2b). No adapter is written yet.

## Licence

MIT. Do not commit anything from `career-data` here.
