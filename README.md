# career-ai

Deterministic engine for a personal, AI-assisted job-scan pipeline.

**This repo contains no personal data.** Career facts, matching criteria, real
search queries, run state and generated reports live in a separate **private**
repository (`career-data`). This split is deliberate: code is shareable,
criteria and history are not.

## Design

Four steps. Only step 2 uses AI.

| Step | Runs | Responsibility |
|---|---|---|
| 1. `collect` | Python | Query sources, normalise, dedupe against seen-state, write `candidates.json` |
| 2. *evaluate* | Claude | Read `05-job-match.md` + `candidates.json`, write one decision per candidate |
| 3. `validate` | Python | Schema, score range, link validity, one-decision-per-candidate. Fails closed |
| 4. `report` | Python | Render `report.md` + one `email-<profile>.html` each, plus `deliveries.json` (recipients from `profiles[].notify.email`); update seen/budget/journal |

Claude never sees credentials, never calls a job API, never sends the email
itself from inside the Python steps. Delivery is a separate, explicitly
authorised action.

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

```bash
pip install -r requirements-apply.txt && python -m playwright install chromium
python -m jobscan.apply approve  a1b2c3     # you approve a queued match
python -m jobscan.apply run --dry-run       # fill forms, submit nothing
python -m jobscan.apply run                 # per apply.mode
python -m jobscan.apply summary             # what is waiting / failed / submitted
python -m jobscan.apply bundle              # redacted failures → paste into Claude Code
```

The LLM never drives the browser; adapters are deterministic code that answers
only from the profile's `profiles/<id>/applicant.yaml`. Unknown required question, CAPTCHA, login wall
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
| LinkedIn, Indeed, Glassdoor | email_alert | no | registered, not implemented |
| Braintrust | email_alert / manual | no | registered; verify access |

Closed platforms are listed so the registry is complete. Direct scanning or
submission against them needs a superseding ADR first.

## Licence

MIT. Do not commit anything from `career-data` here.
