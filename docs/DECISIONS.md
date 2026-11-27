# Decision log

Format: **ADR-n · date · title** — Context · Decision · Consequences.

## ADR-001 · 2026-10-02 · Split code and data into two repositories
Context: the tool needs sharing/portfolio value and holds career-sensitive data.
Decision: `career-ai` (public, no personal data) and `career-data` (private).
Consequences: every config path is relative to a data root passed at run time;
CI on the public repo can never see personal data.

## ADR-002 · 2026-10-02 · Routine for personal use, API for the product
Context: routines run on the owner's own subscription.
Decision: use a Claude Code routine for the owner's own scan; the multi-user
product calls the Claude API with per-token billing and a usage ledger.
Consequences: cost per user must be modelled; the `Evaluator` seam isolates it.

## ADR-003 · 2026-10-02 · The LLM scores; code acts
Decision: Claude writes a schema-validated decision per candidate. Collection,
dedupe, blacklist, validation, rendering, email delivery and any submission are
deterministic code. No model-driven browsing or submission.
Consequences: prompt-injection in postings cannot cause an external action.
*Submission clause superseded by ADR-042 (2026-11-04): deterministic code may submit under its conditions.
"No model-driven browsing" stands.*

## ADR-004 · 2026-10-02 · Application submission is opt-in and bounded
Decision: default `manual`; `assisted` and `auto` behind a master switch with a
dated acknowledgement, caps, allow-listed adapters, and a redacted failure log.
Never: CAPTCHA solving, LinkedIn automation, auto-answering legal questions.
Consequences: expect many "hand to human" outcomes; that is correct behaviour.
*Amended by ADR-017 (2026-10-08): "LinkedIn automation" is no longer a blanket ban; the
CAPTCHA and legal-question rules stand.*
*LinkedIn clause superseded by ADR-042 (2026-11-04): LinkedIn Easy Apply in auto mode, deterministic code only, under its conditions.*

## ADR-005 · 2026-10-02 · Blacklist enforced three times
Decision: filter in `collect`, fail in `validate`, refuse in `apply`.
Defaults seeded: Micro1, Crossing Hurdles, Proxify, Alignerr.
Added in career-data `config.yaml` after the seed (2026-11-05): Recruitment Room (alias
"Recruitment Room - Global"), Pitch N Hire, JobLeads. `tests/test_blacklist_bank.py` pins the
batch-apply bank's six names.
Consequences: removing an entry brings jobs back (blocked jobs are not marked
as seen).

## ADR-006 · 2026-10-02 · Email-forwarding over Gmail OAuth for the product
Decision (provisional): users forward LinkedIn alerts to a per-user inbound
address. Revisit after checking Google's current OAuth verification rules.

## ADR-007 · 2026-10-02 · P0 routine is exposed to untrusted input; mitigate by environment, not by assumption
Context: ADR-003 and ARCHITECTURE §5 claim the model has no tools. The P0 routine
is a full Claude Code session with a shell, a GitHub push credential and the Gmail
connector, and it reads untrusted job text.
Decision: the environment restrictions in GETTING-STARTED Part 5 are mandatory for
P0: custom network allow-list (never "Full"), API keys as proxy-injected
credentials (never in the shell), Gmail as the only connector, recipients limited
per profile by `notify.email` in `profiles/<id>/profile.yaml` (see ADR-009, ADR-011). The ADR-003 claim is amended to "mitigated in P0,
eliminated in P4 when `ApiEvaluator` is a tool-less API call". Email-alert
ingestion (a third untrusted channel) stays off until this is verified on a real run.
Consequences: residual risk is the Gmail connector (can send to any address; the
recipient limit is an instruction, not code) and the repo push credential. Check
both on the first run. Consider a deterministic mailer so the model cannot send.

## ADR-008 · 2026-10-02 · Sources are registry entries with a declared access method; closed platforms are registered, not scraped
Context: the owner wants LinkedIn, Indeed, Glassdoor and Braintrust in the source
list next to Greenhouse and others, and wants to handle access problems when they
occur. These platforms offer no sanctioned open API (verify per platform), and
automated access risks the user's own accounts. Notifying on failure does not
prevent detection or restriction, and detection can look like empty results.
Decision: every source is a registry entry with `access_method` in `public_api |
keyed_api | feed | ats_board | email_alert | manual_channel` (no `scrape`), plus
`terms_reviewed`, `rate_limit`, `redistribution_allowed`. LinkedIn, Indeed and
Glassdoor are registered with `email_alert`; Braintrust with `email_alert` or
`manual_channel` pending verification. Every source reports `SourceHealth` and the
Notifier alerts on degradation, including unexpectedly empty results. Direct
scanning or submission against a closed platform is **not** approved here: it
requires a superseding ADR (scope, per-source opt-in, own machine only, stop on
first block signal, no evasion) before any code is written. Non-negotiable 4 and
ADR-004 stay in force until then.
Consequences: the source list is complete from day one. Nothing in P0 or P2 waits
on closed-platform access. Freshness for those platforms depends on alert emails.
*Superseded in part by ADR-017 (2026-10-08), which is the superseding ADR this one asked
for: it sets the conditions under which direct access to closed platforms is allowed.*

## Provenance
The project originated in the chat at
https://claude.ai/share/e644dc10-0921-4166-8dd1-ac20e5956316
(reference only; the page could not be read when fetched on 2026-10-02, and the
decisions in this log supersede anything in that chat).

## Template

## ADR-n · YYYY-MM-DD · Title
Context: … · Decision: … · Consequences: …

## ADR-009 · 2026-10-02 · Email recipients are per profile, not global
Context: `authorization.yaml` held one `allowed_recipients` list, and the report
rendered one combined email. With several people (PRODUCT: owner plus family,
separate profiles) that would send everyone's matches to everyone.
Decision: each profile declares `notify.email` (originally in `config.yaml`, now its own file, ADR-011). `report` renders
one `email-<profile>.html` per profile with only that profile's matches and
application queue, and writes `deliveries.json` mapping each body to its
recipients. `validate` fails closed if any profile has no usable address.
`authorization.yaml` keeps the permissions (active, allowed actions, submission)
and no longer holds addresses.
Consequences: the routine may email only the `to` list of each delivery entry.
The recipient limit is still an instruction to the model (ADR-007), now backed
by a manifest built by code rather than a list the model reads and matches.

## ADR-010 · 2026-10-02 · CVs are per profile, and the AI picks one per job
Context: CV files were one global `apply.cv_variants` map of placeholder paths,
chosen only by tier. Each user keeps several CVs (general, tech lead, architect,
project manager…) in a Drive folder, one subfolder per variant, with free naming.
Decision: each profile declares `cv.dir` (Drive-style folder, or a folder in the
data repo) and `cv.default`. Variant ids are derived from folder names (person's
name, shared prefix and "resume"/"cv" dropped). The cloud scan cannot reach the
files, so each variant has a card in `profiles/<id>/cv/<variant>.md`; the AI
chooses `cv` per decision from those cards, `validate` rejects unknown ids and
emailable matches without one, and `apply run` resolves the id to a file locally
(PDF over DOCX). A missing file is `CV_MISSING`, never a silent fallback.
Consequences: adding a CV means adding the folder and its card;
`python -m jobscan.cv` shows mismatches between the two.

## ADR-011 · 2026-10-02 · A profile's settings live in its own folder
Context: every per-user setting (email, CV folder, queries, thresholds) sat in a
`profiles:` list inside the shared `config.yaml`, so adding or editing a user
meant touching global config.
Decision: each profile is `profiles/<id>/profile.yaml`; the folder name is the
id and the criteria default to `profiles/<id>/01-knowledge/05-job-match.md`.
`load_config` builds `cfg["profiles"]` from those files, so nothing downstream
changed. `config.yaml` keeps the global settings (sources, budgets, blacklist,
apply, manual channels). Inline `profiles:` still loads (an id defined in both
places is an error), so old data repos keep working.
Consequences: adding a user is adding a folder; a profile's data is
self-contained, which is the shape a per-user table needs later.

## ADR-012 · 2026-10-02 · The applicant is per profile: profiles/<id>/applicant.yaml
Context: `apply run` read one `applicant.yaml` at the data-repo root, so every
queued job was filled in with the same person's details, wrong for a second
profile and the last per-person file outside `profiles/`.
Decision: the applicant (name, contact, pre-approved answers) is
`profiles/<id>/applicant.yaml`, still gitignored and local to the machine that
runs `apply run`; `applicant.example.yaml` is the template beside it. Each
queued job uses the applicant of its own profile. A profile without a usable
file is skipped with a message and its jobs stay `approved`; the run exits 2 if
that leaves nothing to do. The old root-level file is not read as a fallback
(it could put one person's details on another's application); the error says
to move it.

## ADR-013 · 2026-10-02 · The applicant lives inside profile.yaml (supersedes the file split in ADR-012)
Context: after ADR-012 a profile had `profile.yaml` plus a separate gitignored
`applicant.yaml`; two files per person to keep in step.
Decision: `applicant:` (name, contact) and `answers:` (pre-approved form answers)
are sections of `profiles/<id>/profile.yaml`, and `profile.example.yaml` is the
single template for the whole profile. `apply run` reads them from the loaded
profile; a profile with no usable applicant is skipped as in ADR-012. The old
`applicant.yaml` files are not read; the error says to move their contents. The
`applicant.yaml` gitignore rule stays so a leftover file is never committed.
Consequences: the profile file is committed, so the applicant's contact details
are now in the private data repo and visible to the cloud routine, which reads
profile.yaml. Mitigations: the repo must stay private; CLAUDE.md forbids the
routine to read or repeat those sections; they are only filled in if `apply run`
is used. Empty fields still mean "unknown, hand the form back to the human".

## ADR-014 · 2026-10-05 · Spend model usage only where judgement is needed
Context: a scheduled run took 9 model turns and read about 490k cached tokens to
score 8 candidates, 7 of which were obvious discards from title and company. Cost
is dominated by turns (each re-reads the whole context), then by description text.
Decision: (1) `jobscan.pipeline` chains collect, triage, validate, enqueue, report
and the git push, so a run is `prepare`, optionally one scoring write, `finish`,
optionally `commit`; when nothing needs scoring `prepare` finishes the run itself
(one call). (2) A per-profile `prefilter` (junior/mid titles, required stack terms
on described jobs) discards obvious rejects in code, with the reason recorded in
`/tmp/auto-decisions.json`. (3) The model reads a compact brief (500-char excerpts,
`pipeline show` for more) instead of `candidates.json`. (4) `max_to_score` (default
40) caps a run; the rest is deferred, not marked seen. (5) `routine-prompt.md` is
short and self-contained so `CLAUDE.md` need not be read on a normal run.
Consequences: a prefilter reject never reaches the model, so rules must be
conservative: they apply to described jobs only (alert emails always go to the
model), and the terms list is broad. This narrows "broad collection, fine-grained
elimination" slightly; the full reject list is auditable. Validation, the
blacklist, the email recipient rule and the contract are unchanged. The model of the
routine (Sonnet vs Haiku) is a separate, owner-controlled setting.

## ADR-015 · 2026-10-06 · Header-based API keys go through the credential proxy; failed source calls are errors
Context: ADR-007 says API keys must not be in the shell of the routine, which reads
untrusted job text. The environment can inject a credential into requests to an
allowed host. JSearch authenticates with the header `X-RapidAPI-Key`, so it can use
that; Adzuna sends `app_id`/`app_key` as URL query parameters, which a header cannot
carry, so it still needs environment variables. Separately, a failed API call used to
return an empty list, spending monthly budget and hiding a bad key or a blocked host.
Decision: `auth: proxy` on a source in `config.yaml → sources` means the code sends no
key and relies on the proxy (JSearch only today); `preflight` says so instead of
"missing". `jsearch` and `adzuna` raise on a failed call, so `collect` records
"<source>: ConnectionError" in the run's errors and spends no budget.
Operations: `docs/API-KEYS.md` documents where each key comes from and how it is set in
the environment; `python -m jobscan.doctor` makes one real request per source to verify it.
Consequences: a key entered in the proxy is invisible to the code, so a wrong or missing
credential shows up as a source error, not as a preflight line. Adzuna's key remains an
environment variable and so visible to the routine's shell; it is a free read-only job
search key, and the contract forbids printing credentials.


## ADR-016 · 2026-10-06 · JSearch gets a longer timeout and one retry
Context: JSearch `/search-v2` takes about 10 s per call and sometimes more than the
20 s default client timeout. Two consecutive `jobscan.doctor` runs timed out, then a third
passed, and RapidAPI's own test of the endpoint succeeded. A timeout looked like "host
not allowed", which sent the owner to the wrong setting.
Decision: `jsearch.TIMEOUT = 60` and `jsearch.RETRIES = 1`, used by `fetch` and by
`doctor.check_jsearch`. `_http.get_json(retries=n)` retries only timeouts and 5xx; a
401/403/404/429 fails at once, and the `/search` fallback still happens only on a 404.
Other sources keep 20 s and no retry. `doctor` reports a timeout as "timed out, not
blocked, run again" instead of pointing at Allowed domains.
Consequences: a scan can wait up to about 2 minutes per JSearch query in the worst case
(2 attempts x 60 s), which is acceptable for the weekly queries. Still open: whether
`page=1` is supported on `/search-v2` (the provider documents `cursor`); it is sent today
and has been harmless.

## ADR-017 · 2026-10-08 · Stay as close as possible to aiapply.co; supersedes parts of ADR-004 and ADR-008
Context: the owner decided the platform should be as close as possible to
[aiapply.co](https://aiapply.co) everywhere. AIApply bundles, as reported by third
parties (the site itself was unreachable from the development sandbox): tailored resume
and cover letter per job, auto-apply on LinkedIn, Indeed, Glassdoor and company pages
with credits and an "Auto" or "Human-in-the-Loop" mode, a job board, an application
tracker, follow-up emails, interview practice and resume translation. Its most cited
failure is irrelevant matches and filters that do not hold. The comparison is kept in
`docs/REFERENCE-AIAPPLY.md`.
Decision:
1. **Reference product.** `docs/REFERENCE-AIAPPLY.md` is the parity matrix. A feature
   AIApply has and this product lacks is a gap to schedule, not a non-goal. Where the
   two differ on purpose, the reason is written there.
2. **Supersedes ADR-008's "not approved" and ADR-004's "never LinkedIn automation".**
   Direct access to LinkedIn, Indeed, Glassdoor and Braintrust, and Easy Apply, may be
   built, under all of: a new `access_method: owner_browser` (still no `scrape` value);
   opt-in per source in `config.yaml` with `terms_reviewed`; runs only on the owner's own
   machine, never in the cloud routine; the owner's own logged-in browser profile, visible
   by default; slow, capped by `rate_limit`; **stops at the first block signal** (CAPTCHA,
   login wall, "unusual activity", HTTP 403/429), records `SourceHealth: failed` and does
   not retry that day; **no evasion** (no spoofed fingerprints, no proxy rotation, no
   CAPTCHA solving); each adapter tested against recorded pages. For Easy Apply the owner
   must also remove `apply_via_linkedin_easy_apply` from `authorization.yaml →
   forbidden_actions` themselves; code never edits that file. No such adapter is written
   by this ADR: the sandbox cannot reach those sites, and selectors written blind are
   guesses. JSearch already returns listings from the same boards through a licensed API.
3. **Volume is a setting, not a principle.** "Not a mass-apply bot" is dropped from the
   product definition. Defaults stay conservative (fit 85, 3 a day, 10 a week) and the
   owner may raise `apply.auto` caps. These floors do not move: blacklist, deal-breakers
   and language prefilter before any apply step, one application per company per window,
   `authorization.yaml` switch plus dated acknowledgement, and a hand-off to the human on
   any unknown required question.
4. **Not superseded.** ADR-003 and ADR-007: the model scores and drafts, code acts; the
   model never drives a browser or submits, because a posting is untrusted text and
   parity needs the features, not an LLM-driven browser. ADR-004's rules on CAPTCHA and
   on legal or work-authorisation questions. ARCHITECTURE §6: no server-side submission
   for paying users until a lawyer has read the ATS terms. A live interview copilot is not
   planned.
5. **Quality is the difference.** Parity in workflow and features, not in targeting: the
   scan's scoring stays ahead of every apply step.
Consequences: PRODUCT.md "What it is not" and "Out of scope" are rewritten; the roadmap
gains a parity track; built with this ADR are an application tracker (`apply track`,
funnel, follow-ups due) and the Application Kit (`jobscan.kit`: cover letter, CV
tailoring, follow-up email, interview prep, written to `profiles/<id>/03-outputs/`).
The owner still has to correct third-party claims against the real site.
Follow-up 2026-10-08: the `config.yaml` comments now describe `owner_browser`; on
`career-data` main the owner removed `apply_via_linkedin_easy_apply`, `solve_or_bypass_captcha`
and `answer_legal_or_work_authorisation_questions_unless_preapproved` from
`authorization.yaml → forbidden_actions`. Nothing in code reads `forbidden_actions`; the
adapters still hand CAPTCHAs and unknown or legal questions to the human, whatever that list says.
2026-10-09: the owner supplied a saved copy of the aiapply.co landing page and
`docs/REFERENCE-AIAPPLY.md` was corrected against it (job-board size, an API exists, the site does
not name LinkedIn, Indeed or Glassdoor, the resume scanner exists). The owner confirmed the
`forbidden_actions` removal was intended and that CAPTCHAs and legal questions stay with them.
Also built the same day: `jobscan.clip`, which reads schema.org `JobPosting` data from a page
the owner saved and queues it for the next scan, so single postings from the closed platforms
need no adapter, selector or login.

## ADR-018 · 2026-10-06 · Language deal-breakers from a declared `languages` map, enforced in the prefilter
Context: a posting requiring German C2 (and written in German) was scored 66 and emailed.
The model only sees a 500-char excerpt, the requirement sat further down, and nothing
in code or criteria treated language as a deal-breaker.
Decision: each profile declares `languages: {BCP 47 tag: CEFR level | basic/intermediate/professional/native}`
in `profile.yaml`. The prefilter inverts the check: any language not spoken at
`prefilter.working_level` (default professional = C1) is "lacking"; a described job is
discarded in code if it is written in a lacking language (function-word detection) or
demands one near a requirement cue ("fluent German", "Deutsch C1"). "A plus" does not
count. No `languages` key means no language filtering. Supported languages: en de fr nl es it pt.
Consequences: zero model tokens, per-profile, no regex lists to maintain. Alert emails and
short texts still go to the model, so the deal-breaker is also stated in the criteria file.
Heuristic detection can miss unusual phrasing; the auto-discard reason is auditable.
*Numbered ADR-016 when written, which collided with the JSearch entry above; renumbered 2026-10-08. Older commit messages and chat may still say ADR-016.*

## ADR-019 · 2026-10-09 · The model drafts form answers; the owner approves each; legal, consent and pay are never drafted
Context: AIApply fills application forms with answers it writes. This product stops at the first
required question it cannot answer (ADR-004) and keeps models away from the browser (ADR-003,
ADR-007), so every such stop was a manual job. The owner asked for AI-drafted answers.
Decision: the adapter logs each unanswered required question with its type, options and length limit.
`apply questions prepare` turns recent failures into a brief; the model drafts offline, from the CV
cards, the knowledge files and (for job-specific answers) the posting, never from `applicant` or
`answers`; `finish` validates and stores the drafts as `proposed`; the owner approves, rejects or
overrides each (`approve`, `reject`, `set`); only `approved` answers reach a form, after the owner's own
`profile.yaml → answers`, which always win. Code, not the prompt, keeps these away from the model and
stores them as `needs_owner`: legal and work-authorisation, consent and confirmation boxes,
demographic questions, pay, notice period, start date, and any date, email, phone or checkbox field.
A draft is rejected for a link, address, phone number, markup or placeholder, an answer that is not
one of a dropdown's or radio's options, one longer than the field, or a reusable answer that names the
company. `finish` is all-or-nothing, and a decision the owner already made is never overwritten.
Consequences: the loop has a human step on purpose, and the model never touches a browser or a
submission. It needs a dry run on the owner's machine to collect questions, the log pushed to
`career-data`, a cloud session to draft, and the owner's approval before the next run. The scan
routine never runs `questions approve|reject|set` (`CLAUDE.md`). Answers are private data in
`applications/answers.json`. An approved answer is the owner's statement from then on, so approve
only what is true; the model cannot check facts, only keep to the CV.

## ADR-020 · 2026-10-09 · Every application that fails or is never submitted is emailed first, every day
Context: `apply run` stops on anything it is not sure of and records `failed`; the owner asked that
any failed auto-apply be reported by email so they can apply by hand. Before this, a failure sat at the
bottom of the scan email without a mention in the subject, an `approved` job that the runner never
picked up (machine off, run crashed) was not reported at all, and `local-apply.sh` aborted on a failed
run before pushing, so the failures never left the owner's machine.
Decision: the scan email puts one block first, "Apply by hand", listing every `failed` application and
every `approved` one older than 36 hours that was never submitted, each with the reason in plain words,
the link, the CV to use and the kit path. The subject carries "⚠ N to apply by hand". A profile with
such items gets an email even on a day with no new matches. Each profile sees only its own. The block
repeats daily until the owner marks the job `done` or `skip`. The local scripts push what a run
recorded even when the run exits non-zero. Every adapter, including any future site adapter, reports
through the same path: raise `ApplyFailure`, and the item becomes `failed`.
Consequences: the email is sent by the scan routine, so a failure reaches the owner at the next scan
after the local script pushed it, not the minute it happens. A faster path needs a sender on the
owner's machine (SMTP credentials), which this repo will not hold (ADR-007). If the owner never runs the
local script, approved jobs go stale and are reported after 36 hours.

## ADR-021 · 2026-10-09 · A development session may fetch a few public pages when the owner asks; captures live in career-data; credentials never do
Context: the owner asked for `jobscan.clip` to be tested on real LinkedIn, Indeed and Glassdoor pages
by the cloud session itself, offered to change the environment's network settings, and said storing
captured material in `career-data` is fine. ADR-017 allows direct access to those sites only on the
owner's machine.
Decision: a development session the owner has asked may fetch public, logged-out pages through
`python -m jobscan.fetchpage` only: at most 5 URLs per run, one plain GET each with an honest
User-Agent, no cookies, no login, no retry, public https hosts only, a pause between requests. The first
block signal (HTTP 401/403/429/451/999, a redirect to a login or challenge page, a CAPTCHA or "unusual
activity" page) ends the run and that host for the day, and nothing is tried to get past it. The scan
routine never fetches these sites (ADR-017, CLAUDE.md). Pages worth keeping, passed through
`jobscan.redact`, go in `career-data/captures/<site>/` (private) so later sessions reuse them; the
public repo gets only synthetic fixtures. Credentials, passwords, session cookies and tokens are not
stored in either repo (career-data README), and no session logs in to a site from the cloud.
Consequences: the cloud network policy must allow the hosts (Allowed domains in the environment's
settings), and a site may still block a cloud address, in which case the owner saves the page in their
own browser. Easy Apply and any other logged-in step stay on the owner's machine. Moving them to the
cloud would put a login in a session whose model reads untrusted postings (ADR-003, ADR-007), from a
datacenter address, with no way to meet a CAPTCHA the owner handles by hand; that is a separate decision
for the owner, not covered here.

## ADR-022 · 2026-10-12 · A snippet cannot clear a language deal-breaker; the model's own language worries are enforced
Context: two Adzuna jobs ("Fluency in French is mandatory"; "communicate clearly in French with
non-technical business users") were emailed to a profile with `fr-FR: basic`. Adzuna returns a ~500-char
excerpt, so the requirement was never in the text the prefilter or the model saw. The model wrote
"language unclear" / "French likely" yet still surfaced them at fit 60-65. Two further gaps: the demand
check was skipped for texts under `min_description_chars`, and the cue list missed "communicate … in French".
Decision: (1) `demanded_language` runs on any text length (only whole-language detection keeps its
length gate), with cues for communicate/speak/written/ability to/bilingual/Kenntnisse and wider language
names; (2) for a snippet (short, cut off, or from a `SNIPPET_SOURCES` API: adzuna) of an on-site job whose
place is only worked in lacking languages (Wallonia, Flanders, France, a bare "Belgium"), the prefilter
discards it; Brussels, remote jobs and unknown places still reach the model; (3) the brief tags snippets
and the scoring rules say an unclearable lacking language is `discarded`; (4) `validate` fails a
non-discarded decision whose why/caution raises a lacking language (not "a plus", not negated).
Consequences: some Belgian snippets that would have been fine in English are discarded; the reason is
in the report. Not done on purpose: fetching the full page in the scan (the scan never drives a browser,
ADR-021). If that is wanted, it is the owner's call.

## ADR-023 · 2026-10-13 · Development follows the AI-native SDLC playbook with role agents
Context: the owner asked for the Anthropic AI-native SDLC playbook to govern changes, after a scan stopped on a misleading "already finished" message.
Decision: seven role agents in `.claude/agents/` and `docs/SDLC.md`. Each stage commits an artifact (`intent.md`, `spec.md`, `plan.md`, tests, PR); the writer of code does not approve it; merges go through a PR with `pytest` green. The scan routine's contract in `CLAUDE.md` is unchanged.
Consequences: more written trail per change; small fixes may collapse intent, spec and plan into the PR description.

## ADR-024 · 2026-10-13 · Approval gates are hooks; review rules live in REVIEW.md
Context: the SDLC playbook (ADR-023) says skills only make policy likely, hooks make it certain, and managed settings stop individuals widening either.
Decision: `.claude/settings.json` denies the owner-only files and the `apply run` / `questions approve|reject|set` / force-push commands, and runs `scripts/hooks/guard.py` as a PreToolUse gate on Bash and file edits (also blocks pushes to `main`, `--no-verify`, `allow_auto_submit`). `REVIEW.md` defines review passes and Important vs nit. `docs/managed-settings.example.json` is a template the owner installs as managed settings; nothing in the repo can enforce it by itself.
Consequences: the scan routine is unaffected (the pipeline pushes from Python, not through the Bash tool). Changes to hooks, settings, `CLAUDE.md` or `routine-prompt.md` need the owner's explicit say-so.

## ADR-025 · 2026-10-15 · GitHub issues start the SDLC; agents act only through files; labels are the owner's gates
Context: ADR-023 and ADR-024 set the playbook's roles, hooks and review rules. The owner asked for GitHub to be the
ticketing and change-management system, for report-a-problem and suggest-a-feature links in the app, for support
tiers L1 to L3, and for those issues to start the agentic SDLC. The repository is public, so anyone can open an issue,
and issue text is untrusted input to a model that can write code.
Decision: (1) three issue forms (problem, feature, help), blank issues off, each with a privacy tick and `stage:intake`;
the scan email, each failed application and `python -m jobscan.feedback` open them pre-filled with the version, the day
and, for a failure, the error code and site only. (2) The `sdlc` workflow starts a stage only when the owner opens an
issue, or a person applies an `agent:*` label; a label by a bot, or an issue by anyone else, starts nothing. (3) Agents
get files, not powers: no push, merge, label, GitHub or web. A deterministic `jobscan.sdlc check` rejects changes outside
the stage, to protected paths (workflows, `.claude/`, `CLAUDE.md`, `REVIEW.md`, `routine-prompt.md`, ADRs, dependencies,
authorization, config, profiles, scripts) and added credentials, emails or phone numbers; only then does the workflow
commit, push to `agent/*`, open a draft PR and post the report. (4) Each stage waits for a human gate: the next label.
Build is followed by a read-only reviewer and security-reviewer pass; a human merges under branch protection. (5) L1, L2
and L3 support, a reviewer, a security reviewer and a release manager join the seven roles of ADR-023.
Consequences: a stranger can file but cannot spend the API budget or move code. Nothing the agents write reaches `main`
without a human. The cost is a human click at every gate and API credit per stage. The workflow needs the Claude GitHub
App, an API key secret and three repository settings (docs/SDLC.md), and has been verified by tests of its rules, not
yet run on GitHub. Workflow-token pushes start no other workflow, so the stage starts `tests.yml` explicitly.

## ADR-026 · 2026-10-22 · Email links record "I applied" / "Not interested" through a GitHub issue
Context: an item under "Waiting for your decision" stays until a CLI command (`done` / `skip`) is typed, which the owner cannot do from a phone, so jobs applied to by hand (or ignored) kept reappearing.
Decision: each waiting, failed and stalled item in the email gets two links that open a pre-filled issue (`done KEY8` / `skip KEY8`, label `job-decision`) in the data repo. The owner presses Submit (GitHub login is the authentication); `docs/decide-workflow.yml`, installed in `career-data`, runs `jobscan.decide` for the repo owner only, accepts only that exact title form, commits `applications/queue.json`, comments and closes the issue. No server, no new hosting, no secrets. `approve` is deliberately not reachable this way. Items already submitted are never overwritten.
Consequences: two clicks instead of a command. The workflow must be copied to `career-data` once; without it the links open an issue nobody processes. Later versions (dashboard, history, auth, OAuth) are in ROADMAP "Owner portal" and should reuse the same `decide` module.

## ADR-027 · 2026-10-22 · Admin bypass on main, pull requests only
Context: SDLC.md said no bypass, but the owner is the only Code Owner (`*` in CODEOWNERS) and cannot approve their own PRs.
Decision: ruleset protect-main allows the Repository admin role to bypass for pull requests only. Direct pushes to main stay blocked. Agent PRs are merged only after pytest is green.
Consequences: the owner can merge their own PRs; for agent PRs, discipline replaces a technical block.

## ADR-028 · 2026-10-22 · Claude GitHub App installed on all repositories
Context: SDLC.md said install it on the repository; the owner chose all repositories.
Decision: the App has access to all repos. ANTHROPIC_API_KEY and the sdlc workflow exist only in career-ai.
Consequences: career-data has no agents, no secret and no workflow; new repos inherit the App but need their own workflow and key to use it.

## ADR-029 · 2026-10-23 · Location is a per-user preference with a compensation-gated relocation override
Context: owner prefers remote/hybrid/onsite from Bangkok, open to relocating anywhere if compensation is good.
Decision: location is data in each profile; no deterministic location rejection; Evaluator scores location fit and checks compensation vs the relocation threshold.
Consequences: more onsite-elsewhere roles in the digest; compensation check must handle missing pay; visa/work-authorisation questions stay human-only.

## ADR-030 · 2026-10-23 · SDLC agents authenticate with the owner's Pro subscription token
Context: an API key bills per token on top of the Pro subscription, and the Console plan had $0 credit; the owner wants no cost beyond Pro.
Decision: the sdlc workflow uses claude_code_oauth_token from the repository secret CLAUDE_CODE_OAUTH_TOKEN, created with `claude setup-token` (valid 1 year, renew before it expires). Allowed only for the owner's own repository and work, through the unmodified claude binary via anthropics/claude-code-action, with every run started by the owner (trusted-author gate and owner-applied agent labels). Never used in the product, never shared (anyone else uses their own subscription), never used for automatic responses to the public. ANTHROPIC_API_KEY is removed and must stay unset because it outranks the OAuth token. Usage credits stay off.
Consequences: the cost ceiling is the Pro usage limits, shared with the owner's own use. Anthropic's docs describe setup-token for CI, but Consumer Terms 3.7 bars scripted access unless explicitly permitted; this is personal use on the documented path, not legal advice, to be re-checked before any multi-user phase. A leaked token is account-level (model requests and quota burn, not chats) and revocation reliability is disputed, so the token lives only in Bitwarden and the repository secret. Whether the model process can read the token is being audited; no claim is made until then.

## ADR-031 · 2026-10-23 · Harden sdlc token handling
Context: an audit of the sdlc workflow asked whether a prompt-injected agent could read or leak `CLAUDE_CODE_OAUTH_TOKEN`. The token must be present in the `claude` process (it authenticates the model calls), and that process's Read tool runs as the same user as the runner. So non-negotiable 2 (secrets never in repos, never in the model context) holds for the repository, the model context and the logs, but not for the process environment. Separately, the agent's issue comment, review and test output live under the gitignored `.sdlc/`, so `git status` never listed them and `check` never scanned them, and the post step published them even after a failed check.
Decision: (1) `check` reads `.sdlc/comment.md`, `review.md`, `pytest.txt` and `labels.txt` from disk and scans them: credentials in all four, email and phone in `comment.md` and `review.md`. (2) The post step runs `python -m jobscan.sdlc scan` once more, because the reviewers and the test run write after the first check; a run that is blocked (check failed, reviewer reject failed, or the scan finds something) posts only "Blocked by the safety check. See the run log." and applies no agent-requested label. (3) `anthropics/claude-code-action` is pinned to commit 6b6870e649b5ff408753befeaee5fc7989d4e6a9 (v1). (4) Both action steps set `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB: "1"`, which strips credentials from Bash, hook and stdio MCP children but not from the `claude` process. (5) `.claude/settings.json` denies `Read(//proc/**)`, `Read(//home/runner/.ssh/**)`, `Read(//home/runner/.config/**)` and `git diff --no-index` (in two forms, because the rule matches by prefix); the checkout under `/home/runner/work` stays readable.
Consequences: fixed: unscanned agent text reaching the public issue, posting after a failed check, a floating action tag, tokens inherited by Bash and pytest children. Still open and unverified: (a) whether a headless Read allowed as bare `Read` can open paths outside the workspace such as `/proc/self/environ`, and whether the `Read(//proc/**)` deny stops it (the docs call Read denies best-effort for built-in tools); (b) whether `git diff --no-index` on a `/proc` file prints anything; (c) how `base-action/src/run-claude.ts` builds the child `env`, which was not read; (d) the scrub leaves `GITHUB_TOKEN` and `GH_TOKEN` in place by design and the job sets `GH_TOKEN` for every step, so the agent's children and the later `pytest` step still see a token with this job's write permissions; (e) when `allowed_non_write_users` is unset, the action may write its own token into `.git/config` (origin URL) although `persist-credentials: false` is set. Scrubbing also installs no sandbox: bubblewrap is only installed by the action when `allowed_non_write_users` is set. Encoded or split tokens are not matched by the credential regex. Follow-ups, not done here: job-level `GH_TOKEN` moved to step level, running the repository's tests without a token, and the sandbox.

## ADR-032 · 2026-10-26 · Usage budget gate for the sdlc workflow
Context: with ADR-030 the agents spend the owner's Pro usage limits, not dollars, and nothing capped how much agent time the workflow could use in a day or a week.
Decision: a "Budget gate" step right after "Decide what to run" sums the agent minutes of earlier sdlc runs over a rolling 24 hours and 7 days (`jobscan.sdlc.budget`, pure, tested without network) and stops the stage when either cap is exceeded: it sets `stop=true`, reports on the issue (mentioning the owner) and annotates a warning; the job stays green. Caps are the repository variables `SDLC_MAX_AGENT_MIN_24H` and `SDLC_MAX_AGENT_MIN_7D`; unset or non-numeric means 60 and 240 (never unlimited), 0 blocks everything, exactly at the cap is allowed. A run counts only if it lasted 30 seconds or more, is not cancelled and is not the current run. Duration is `updated_at - run_started_at`, an approximation. If the run history cannot be read the stage is blocked. `jobscan.sdlc` became a package (`sdlc/__init__.py`, `__main__.py`) so the budget module sits beside it; `python -m jobscan.sdlc` is unchanged.
Consequences: a runaway day cannot drain the subscription; the cost is that a busy day may refuse a stage until usage slides out of the window. Minutes are not Pro quota: the caps are a proxy the owner tunes. Concurrent runs can each pass the gate before either is counted. The gate runs before the branch checkout, and the existing report step still applies the stage label as for the other gates.

## ADR-033 · 2026-10-26 · Drop the subprocess env scrub setting
Context: the first real sdlc run (run 40296239640, intent stage on issue #37) failed before the agent started with "error: bubblewrap is required for subprocess env scrubbing and isolation". `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB: "1"` (ADR-031 item 4) requires bubblewrap, which the runner does not have. Nothing ran.
Decision: the setting is removed from both `anthropics/claude-code-action` steps; nothing else in the workflow changes, and a test asserts it stays absent.
Consequences: the token therefore stays in the environment of subprocesses such as pytest in the build stage, which ADR-031 had meant to fix. Options still open: install bubblewrap on the runner (unverified that it would work), or run the tests in a step without the token.

## ADR-034 · 2026-10-27 · Closes instead of Refs in the draft PR body
Context: the draft PR body began with "Refs #N", which GitHub does not treat as a link: the PR was missing from the issue's Development sidebar and merging did not close the issue.
Decision: the body (`jobscan.sdlc.pr_body`) starts with "Closes #N" and adds "Stage reports are on the issue: #N." The issue comment gets a "PR: #n" line when an open PR exists for the branch (never on a blocked run), and the issue's `type:*` labels are copied onto the PR, best effort (never `agent:*` or `stage:*`).
Consequences: the PR is linked and merging closes the issue. Trade-off: an early merge of the intent-only draft PR would close the issue before spec, plan and build; the checklist in the PR body and docs/SDLC.md say to merge only when it is done, and merging stays a human act.

## ADR-035 · 2026-11-02 · Scope GH_TOKEN to the steps that need it
Context: ADR-031 and ADR-033 left open that the job-level `GH_TOKEN` was inherited by the agent's children and by `pytest`, which runs code the build agent wrote. Reading `anthropics/claude-code-action` at the pinned commit 6b6870e6 also showed that, with `allowed_non_write_users` unset, `replaceCheckoutCredentials` (`src/github/operations/git-config.ts`, lines 130-133) sets `origin` to `https://x-access-token:<token>@github.com/...`, so the token lands in `.git/config` even though `persist-credentials: false` is set on checkout. The `extraheader` is only removed, never written, by the action.
Decision: (1) The job-level `GH_TOKEN` is removed. It is set only on "Budget gate", "Fetch the issue and PR comments (gh)", "Commit and push the artifact, open the draft PR, start the tests" and "Post the report, apply the stage label". (2) The `gh` calls and `pip install` were split out of "Frame the issue..." so that step and the dependency install run without it. (3) A step after each action run resets `origin` to the plain URL and unsets any credential helper or extraheader before the safety check, the reviewers' check or pytest run. The push step uses its own URL, so it does not rely on `origin`. (4) `tests/test_sdlc_token_scope.py` parses the workflow: no job-level token, only the named steps have `GH_TOKEN`, pytest steps carry no secret env, `origin` is reset after each action step. The pinned SHA is unchanged.
Consequences: `pytest` and agent-written code run without the repository token, except `GITHUB_TOKEN`/`GH_TOKEN` still exist inside the `claude` process environment (the action sets them) and the push and post steps still run repository `python -m jobscan.sdlc` code with the token (`pr-body`, `report_header`, `scan`, the budget module). Verified only by the parse test and by reading: GitHub Actions cannot be run from here, so the first real run should be checked (the reset steps, the split steps, and that the push still works).

## ADR-036 · 2026-11-02 · Post and push import jobscan from the trigger commit; agent writes to .git/ are blocked or reset
Context: ADR-035 scoped `GH_TOKEN` to the steps that call `gh` or `git push`, but the push and post steps still ran `PYTHONPATH=src python -m jobscan.sdlc ...` against the working tree. The build agent may write under `src/**`, so code it wrote could run in a step that holds the token. A first fix took a `git archive origin/main` copy, but that left two gaps. (1) The agents can write under `.git/`: the build stage has `Write,Edit` plus `Bash(python -m pytest:*)` (tests it wrote run arbitrary code) and the review stage has `Write`. Nothing in the repository stopped it: `.claude/settings.json` denies only owner yaml files and a few `Read` paths, `scripts/hooks/guard.py` blocked only three file names, `PROTECTED` has no `.git/**`, and `check` reads `git status`, which never lists `.git/`. A forged `.git/config` (`core.fsmonitor`, `core.hooksPath`, `include.path`, `url.<x>.insteadOf` to redirect the token's push, `credential.helper`, `filter.*`, `diff.external`) or `.git/hooks/*` runs a command in the next git call, and `git archive` reads that same object database. (2) `python -m` puts the current directory first on `sys.path`.
Decision: (1) The trusted code is a second `actions/checkout@v4` with `ref: ${{ github.sha }}` (the trigger commit), `path: trusted`, `sparse-checkout: src` and `persist-credentials: false`, not `git archive`. It is taken after the stage agents and again after the review agents, each time after `rm -rf trusted` (the folder is added to `.git/info/exclude` so `check` and `git add -A` ignore it), and `TRUSTED_SRC` is set to `$GITHUB_WORKSPACE/trusted/src`. Every jobscan call after the stage agents uses `PYTHONPATH="$TRUSTED_SRC" python -P -m jobscan.sdlc`; `-P` keeps the current directory off `sys.path`. (2) Blocked: `scripts/hooks/guard.py` refuses `Write` and `Edit` on any path with a `.git` component. This does not stop code run by `pytest`, so (3) Reset: after each agent run the reset step unsets `include.*`, `core.fsmonitor` and `core.hooksPath`, removes every other `.git/config` key checkout did not write (a keep-list, so `url.*`, `credential.*`, `filter.*`, `alias.*`, `http.*`, `diff.external` and `core.worktree` go too), sets `remote.origin.url` to the plain URL, deletes `.git/config.worktree` and empties `.git/hooks`. (4) Every git call in a step that holds the token goes through `git() { command git -c core.hooksPath=/dev/null -c core.fsmonitor=false "$@"; }`; the job sets the same two values through `GIT_CONFIG_COUNT` for any git that `gh` or python starts, and the token steps set `GIT_CONFIG_GLOBAL=/dev/null` and `GIT_CONFIG_NOSYSTEM=1`. (5) Tests: `tests/test_sdlc_trusted_code.py` and `tests/test_sdlc_git_hygiene.py` parse the workflow, and the latter runs both reset scripts against a poisoned throwaway repository.
Consequences: code that runs with the token is the code at the trigger commit (the default branch), and git in those steps does not run hooks, fsmonitor, filters or credential helpers from a forged config. A change to `jobscan.sdlc` made on the branch is not used by its own build run; that is intended. Not covered: `.git/HEAD`, `refs/`, `packed-refs` and `objects/` are not reset, so an agent that moves HEAD or plants a `refs/replace` ref could change what `git diff HEAD` and the push see (a pre-agent HEAD check and `GIT_NO_REPLACE_OBJECTS=1` would close this; not added because it cannot be tested here), and `~/.config/gh` is not reset. The `claude` process environment still holds `GH_TOKEN` and `GITHUB_TOKEN` (ADR-031 item d), still open. Not verified by a real run: GitHub Actions cannot run here, so the first run must show the trusted checkout succeeding, `check` ignoring `trusted/`, and the post step importing from `$GITHUB_WORKSPACE/trusted/src`.

## ADR-037 · 2026-11-02 · The privileged sdlc job runs no repository test code
Context: the `claude` process in `sdlc.yml` holds `GH_TOKEN`/`GITHUB_TOKEN` and the Claude GitHub App token, which job `permissions:` do not limit. The build stage allowed `Bash(python -m pytest:*)`, so a `conftest.py` or test the agent wrote ran inside that process and could read or send those tokens, or write to `GITHUB_ENV`/`GITHUB_PATH` to change later steps. The workflow's own dependency install and "Run the tests once more" step also ran agent-written code after the second trusted load and before the post step.
Decision: (1) Tests run only in `tests.yml` (read-only token, no secrets); the push step still dispatches it with `gh workflow run tests.yml --ref "$BRANCH"`. (2) `BUILD_TOOLS` is `DOC_TOOLS`: no pytest, pip or other repo-code execution in any stage's allowed tools. (3) The dependency install and "Run the tests once more" steps are removed. `budget`, `check`, `scan`, `pr-body`, `report_header`, `prompt` and `tests_note` import only the standard library and were run under `python -P` in a venv with no packages. (4) The build prompt and the developer and tester role prompts say: write tests, do not run them, say so in the report. The post step adds a fixed line (`jobscan.sdlc.tests_note`) that tests were not run by the agent or the workflow and that the `pytest` check on the PR is the evidence; `.sdlc/pytest.txt` is no longer posted, so an agent cannot forge a result. (5) The review stage reads `.sdlc/checks.txt`, written by a step with `GH_TOKEN` on that step only: after the push for a build (for the pushed SHA, taken from the push step's output), or before the agent for a `review` or `release` stage (current HEAD). It is written after the build agent has finished, so the agent cannot forge it. First line `commit: <sha>`, then one `name: status conclusion` line per check run; on a failed or empty call it holds `Could not read check results for <sha>: <reason>`, and the step stays non-fatal. The reviewers quote the commit line, say "not known" for queued, in_progress or unreadable results, and claim passing tests only for a `pytest` check that is completed success for that commit. (6) `Read(//proc/**)` (already in `.claude/settings.json`, ADR-031) is also passed as `--disallowedTools` to both agent steps. It applies to the Read tool and to file commands Claude Code recognises in Bash, not to a process that opens files itself; Bash is limited by the allow-list.
Consequences: the build agent cannot iterate on failing tests; failures show in the dispatched tests run, and the owner re-applies `agent:build`. Build quality may drop and costs a round trip per failure. Not fixed: the `claude` process still holds the tokens and the App token; the two-job split (a future ADR) is the remaining step. `Write`/`Edit` of `.claude/settings.json` mid-run is refused only after the fact by `check`. Not verified by a real run: the `check-runs` steps (the first real run must show whether the job token needs `checks: read`; the job lists explicit permissions, so `checks` is `none`, and the repository is public, which may be enough; it is not added until a run shows it is needed), the `tests_note` call and the new `--disallowedTools` value.

## ADR-039 · 2026-11-02 · No-op issue events get their own concurrency group
Context: issue #50 (throwaway): run 41410127118 (`issues: opened`, job `stage`) was cancelled after 2 s with "Canceling since a higher priority waiting request for sdlc-issue-50 exists". Runs 41410127208 (`labeled` type:bug) and 41410127694 (`labeled` stage:intake) both ended at the decide step with "not running: not an agent:* label", so no intent ran until the owner applied `agent:intent` by hand (run 41411516257, which worked). Cause: the issue forms apply `type:*` and `stage:intake` at creation, so GitHub fires `opened` plus one `labeled` per label within the same second. All shared the workflow-level group `sdlc-issue-N` with `cancel-in-progress: false`, and a newer pending no-op run replaced the older pending real one. On #47 the same race happened and the real run survived on timing. This is the reading from the evidence; the run history was not re-read by this change.
GitHub docs (source of the "Control the concurrency of workflows and jobs" page, read in `github/docs`, the rendered site being unreachable from the dev sandbox): "This means that there can be at most one running and one pending job in a concurrency group at any time. When a concurrent job or workflow is queued, if another job or workflow using the same concurrency group in the repository is in progress, the queued job or workflow will be `pending`. Any existing `pending` job or workflow in the same concurrency group, if it exists, will be canceled and the new queued job or workflow will take its place." and "To also cancel any currently running job or workflow in the same concurrency group, specify `cancel-in-progress: true`." Also: "Jobs or workflow runs in the same concurrency group are processed in first-in-first-out (FIFO) order … ordering is not guaranteed." The docs do not say whether a workflow run whose jobs are all skipped by `if` takes the workflow-level group, nor whether a skipped job takes its job-level group.
Decision: (1) The workflow-level group is `sdlc-issue-N` only for an event `decide` would act on, and `sdlc-noop-<run id>` (unique, defined for every run) for any other, so a no-op event cannot replace or queue behind a real run. Because the docs are silent on skipped runs, the group key, not an `if`, carries the guarantee. (2) The job `if` has the same condition, so a no-op run skips before checkout, the budget gate and the agent. (3) The condition is `decide` as an expression: not a PR, issue open and unlocked, and either `opened` by OWNER, MEMBER or COLLABORATOR, or `labeled` by a `User` whose login does not end `[bot]` with a label that is a key of `LABEL_TO_STAGE`. The two lists are the code's `TRUSTED` and `LABEL_TO_STAGE`, and `tests/test_sdlc_concurrency.py` fails if the YAML and `decide` disagree for any case in its table. (4) Unchanged: `cancel-in-progress: false`, the budget gate, the stage input gate, token scope (ADR-035), trusted-code loads (ADR-036), ADR-037, and one agent run per stage. Two real runs for one issue still share the group and queue as before; `decide` still runs in the job and stays the authority.
Consequences: a new issue from a form starts exactly one intent run and no cancelled run, as far as the docs and the tests show. No-op runs still appear in the Actions list, finishing as skipped. GitHub compares strings in expressions case-insensitively and `decide` does not; no label or association value in use differs from another only by case, so no case changes. Not verified by a real run: that GitHub accepts the expression in `concurrency.group` (the docs allow the `github` context there and `fromJSON`, `contains`, `endsWith`, `format` are documented expression functions, but the workflow was not run), that two issues opened back to back each get exactly one intent run and no cancelled run, that a skipped no-op run is not itself shown as a failure, and the ordering of a real run against a no-op run in different groups. The owner's check after merge: create two throwaway issues from the form, one right after the other, apply no label, and expect one run doing the intent work for each and no cancelled run.

## ADR-038 · 2026-11-04 · Apply-session hardening: consent stop, no slug guessing, adaptive pacing
Context: A 15-application Greenhouse batch run showed four recurring failures. Consent, NDA and declaration dropdowns blocked submission. Slugs cannot be derived from job IDs. Inertia reads hit 429s at a fixed pace. Stale CV text could be reused silently. Dedup relied on re-checking live pages.
Decision: The engine never answers consent-type fields (CONSENT_PENDING => stop and hand over, per non-negotiable 4). Slugs come only from a verified cache; a miss is NOT_FOUND. Request pacing is adaptive (2 s, then 10 s after the second 429 in a run). Success is recorded only when the final URL ends in /confirmation, with applied_at and confirmation_url stored. CVs are checked against a SHA-256 manifest in career-data. The blacklist stays single-source in config.yaml. Run summaries go to runs.jsonl behind FileStore (a Postgres table waits for P3).
Consequences: Some forms always need a human click. Browser batch sessions run in the Claude desktop app and are an LLM-driven exception to non-negotiable 3, covered by Rui's standing per-session approval and never used for server-side or multi-user submission. The skill and the engine share one vocabulary: SUBMITTED, SKIP/NOT FOUND, EXTERNAL/LOGIN-NEEDED, CONSENT-PENDING, SKIP-RECOMMENDED, BLOCKED. Untested: real Greenhouse behaviour for Retry-After; verify against a live 429 before relying on it.

## ADR-040 · 2026-11-04 · Owner-run assisted apply is an owner-only exception, not product behaviour
Context: the owner submits LinkedIn Easy Apply and similar applications through
the browser batch sessions that ADR-038 already allows, after approving one
numbered list each time. Applied to the product, this would break
non-negotiables 3 and 4 and ADR-003/004 (LinkedIn access conditions: ADR-017).
Decision: this is an owner-only, human-approved exception on the owner's own
accounts, and it is never shipped, documented or sold as product behaviour. It
adds no mechanism of its own; ADR-038's batch-session rules are the only route.
The product keeps deterministic adapters, the ADR-017 conditions for any direct
LinkedIn access, and human-only consent and work-authorisation answers. Standing
answers live in memory (single source); the skill's answer bank is the fallback.
Consequences: the owner accepts LinkedIn account-restriction risk (its User
Agreement restricts automated access; verify current text). Every submission
needs per-list approval, and consent and work-authorisation answers are
reviewed in that list. Generalising this to other users needs legal review and
a new ADR first.

## ADR-041 · 2026-11-04 · Engine implementation of ADR-038: consent, confirmation, verified slugs, run log, CV freshness
Context: ADR-038 (apply-session hardening) states the rules. This records how the engine enforces them in code, and what the owner should expect.
Decision: (1) `classify_field` marks consent, privacy, NDA, declaration and acceptance labels; the FormAdapter never answers them, even with a pre-approved yes, and stops before submit as `consent_pending` (ADR-020 hand-over). Legal and work-authorisation questions keep their stop (ADR-019). (2) A submit is confirmed only when the final URL path ends in `/confirmation`; `applied_at` (UTC) and `confirmation_url` are stored on the queue item and its attempt, and the runner skips any record with `applied_at`. Thank-you text elsewhere is `SUBMIT_UNCONFIRMED`. (3) Greenhouse references keep their host (`job-boards.greenhouse.io` or `job-boards.eu.greenhouse.io`). `state/slug_cache.json` is written only after a 200 for that form page; a miss is `NOT_FOUND`, with no guess and no network call. (4) `logs/runs.jsonl` gets one appended line per job the runner looks at (`Store`/`FileStore`, relative names only). (5) `jobscan cv-check` compares the CVs named in `cv_manifest.json` with their SHA-256 and names the changed or missing ones. (6) `AdaptiveLimiter` (2 s, then 10 s after the second 429 in a run; Retry-After honoured) is per run; it is not yet wired into the fetchers.
Consequences: a consent box always reaches the owner, and some forms that used to submit unattended now stop by design. Whether real Greenhouse submits redirect to `/confirmation` and how consent markup looks are not verified against live pages; ADR-038 already lists the Retry-After check as untested. The queue, answers and failure-log modules still use their own helpers rather than `FileStore`.

## ADR-042 · 2026-11-04 · LinkedIn Easy Apply in auto mode, by deterministic code only; supersedes the submission clause of ADR-003 and the LinkedIn clause of ADR-004 *(accepted by the owner 2026-11-04; implemented in `apply/authz.py`, `apply/linkedin.py`, `apply/policy.py`)*
Context: the owner wants unattended applications on LinkedIn Easy Apply within caps, and asked for a browser
executor that a model drives. ADR-017 allowed direct LinkedIn access under conditions but wrote no adapter. ADR-040
is an owner-only manual exception and is not product behaviour. ADR-003, ADR-007 and ADR-017 §4 keep the model out
of the browser, because a posting is untrusted text that can carry instructions. A model-driven browser cannot be
bounded by code in the way a fixed adapter can, so this ADR puts the executor in code, not in a model.
Decision:
1. **Adapter `linkedin_easy_apply`.** `mode: auto` is allowed only when all of these hold: `authorization.yaml →
   application_submission.master_switch` is `true`; the adapter's own `enabled` flag is `true`; and a dated
   `linkedin_tos_acknowledgement` exists, written by the owner. Otherwise the run refuses, and the adapter may run
   only as `manual` or `assisted`. The adapter has its own caps, with conservative defaults: 2 a day, 5 a week, one
   per company per 30 days, fit at least 85, confidence `high`, tier `core` only.
2. **Jobs come only from the owner's own forwarded LinkedIn alerts** (`email_alert`, ADR-017). There is no
   LinkedIn scraping, no search crawling and no fetch of listings the owner did not forward.
3. **Browser executor: deterministic code, inside `apply run` only.** No LLM is in the browser loop, and no model
   decides a click, a fill or a submit. The executor:
   - holds no secrets in the page context or in logs, and uses a dedicated browser profile, never the owner's
     general profile;
   - fills a field only from the answer bank (`answer_bank.yaml`, owner-written, approved answers only);
   - stops and hands the job to the human on: an unknown required question; any consent, privacy or declaration
     box (ADR-041); any legal, work-authorisation or demographic question; a CAPTCHA; a login wall; or a changed layout;
   - treats every page and posting text as untrusted data. It is never an instruction, and nothing in it can
     change a field, a cap or a rule.
4. **Kill switch.** The first LinkedIn warning, challenge or "unusual activity" page halts the whole run, records
   the event, and sets a cooldown (default 7 days) during which the adapter refuses to start. Nothing retries that day.
5. **Kept from ADR-004, unchanged:** the blacklist is refused in `apply` as well as in `collect` and `validate`
   (ADR-005); logs are redacted at write time; `--dry-run` fills and never submits; one submission is recorded
   only when a `/confirmation` page is reached (ADR-041); no CAPTCHA solving or bypass; no evasion (no spoofed
   fingerprints, no proxy rotation).
6. **Where it runs.** Only on the owner's own machine, in `apply run`. Never in the scan routine, never in the
   cloud, never for another user (ARCHITECTURE §6 product implication stands).

Not superseded: the model never drives a browser and never submits (ADR-003 for the model, ADR-007, ADR-017 §4).
Only deterministic code may submit, and only under this ADR. Legal, consent and work-authorisation questions stay
human-only (ADR-019, ADR-041).

Consequences: the owner accepts LinkedIn account-restriction risk. Its User Agreement restricts automated access
(verify current text before relying on it). The acknowledgement is the owner's own dated statement, not something
code or a model writes. Build order: this ADR is accepted, then the schema and adapter with fake-page tests, then
career-data. Acceptance tests run on fakes with no network. Not verified against live LinkedIn pages: selectors are
written from recorded fixtures only, and the first real run is a dry run on the owner's machine.

## ADR-043 · 2026-11-05 · Design docs live only in career-ai/docs; Project holds live run state only
Context: ARCHITECTURE, PRODUCT, DECISIONS and ROADMAP existed both in the Claude Project and in career-ai/docs. The Project copies stopped at ADR-007 and used different numbering from the repo (location is ADR-029 here).
Decision: git is the single source of truth for the design docs. The Project copies are removed. apply-state-*.md stay in the Project while a run is live and are archived into career-data/apply/log.csv when the run closes. Nothing personal moves into career-ai.
Consequences: design sessions read the docs from the repo. A run is not closed until its rows are in log.csv. Docs-only change; no code.

## ADR-044 · 2026-11-05 · Work-authorisation standing answers only after the owner's acknowledgement; sworn, I-9, citizenship and clearance questions are always by hand
Context: application forms ask about work authorisation and sponsorship. A saved standing answer saves time, but once submitted it is a statement made for the owner on every job it reaches. Some questions are sworn or legal attestations that code must never answer.
Decision: `jobscan.bank.lookup` returns a work-authorisation or sponsorship answer only when `authorization.yaml` in career-data has `work_auth_standing.acknowledged_on` set to a valid date. Sworn-attestation, I-9, citizenship and clearance questions always return NEEDS_ANSWER, whatever the bank or profile says. Code never sets `acknowledged_on`; only the owner does.
Risk: a standing answer applies to every job, so if the owner's status changes (visa, residency, right to work), the saved answer becomes wrong and keeps being used until the owner changes it. Mitigation: the owner edits `acknowledged_on` when the status changes; every submission is recorded in `logs/apply/` (ADR-045) so the owner can review what was said.
Consequences: a missing or malformed acknowledgement means the question goes to the owner. The policy is tested in `tests/test_answer_bank_v2.py`.

## ADR-045 · 2026-11-05 · Hand-off route: the owner attaches the CV and submits; the run verifies by confirmation URL or Gmail and records one line per outcome
Context: some sites cannot be submitted by code reliably, and the owner has to finish those in their own browser. Runs also need an auditable record of what was submitted, without the URLs' tokens.
Decision: where code does not submit, the owner attaches the CV and submits in their own browser. The run then verifies the submission from the confirmation URL or a Gmail confirmation and appends an `ApplyOutcome` line to `logs/apply/<site>-<date>.jsonl` in career-data. Every URL in a line loses its query string and fragment before it is written. A SUBMITTED line must name its verifier (`confirmation_url`, `gmail` or `human`); `human` is used only for a submission the owner confirms in their own words. Code never clicks submit on a site it does not own (ADR-040, ADR-042 unchanged).
Consequences: outcomes are one JSON line each and append-only; corrections are new lines. The scan routine does not write these files.
*Amended in part by ADR-047 (2026-11-05): a second verifier, `site_applied_list`.*

## ADR-046 · 2026-11-05 · career-data is the only source of identity facts; career-ai carries no personal data and a build guard checks that
Context: the skill bank and career-data disagree on the owner's legal name, phone number and home base. Code cannot decide which is right, and a wrong identity on a form is a false statement.
Decision: name, phone, address and home base live only in career-data. Where sources disagree, the answer bank holds a `CONFLICT` entry listing each value and its source, and the owner decides (questions in career-data `docs/OPEN-QUESTIONS.md`). career-ai's `tests/test_no_personal_data.py` fails the build when a tracked file has an email address outside reserved domains, or a phone-shaped number outside `tests/`. The owner-specific layer compares every tracked file with literal strings from the file named in `CAREER_PII_PATTERNS_FILE` (a CI secret); without that secret the layer is skipped and reported as skipped, not as passed.
Consequences: a new identity fact is added to career-data first. Until the CI secret is set, names and numbers are guarded by review only.

## ADR-047 · 2026-11-05 · Arc (arc.dev) is a registered owner-run site; the site's own Applied list is an accepted verifier; a disabled Submit is a stop
Context: the first Arc run (4-5 Nov 2026) applied through Arc's Fast apply dialog in the owner's browser
session (ADR-038, ADR-040). Fast apply has no review page and no confirmation URL: success is an
on-page "Application sent" message plus a row in the site's Applied tab. One job also showed a required
free-text box the browser could not reach and a disabled Submit button. The expected-rate field is also
locked to "save as new expected rate", so every submit rewrites the owner's Arc profile rate.
Decision: (1) Arc is registered as `manual_channel`, status `registered`. Jobs come only from the owner's
saved searches; applying happens only in the owner-run, human-approved browser session. No adapter, no
scraping, no code submission. (2) `ApplyOutcome.verified_by` gains `site_applied_list`: the run read the
site's own Applied list after the submit. It is valid only for sites that give no confirmation URL;
where one exists, `confirmation_url` stays the verifier (amends ADR-045). (3) A disabled final button, or
a required field with no reachable input, stops that job as BLOCKED. Neither code nor a run removes a
`disabled` attribute or bypasses a site's validation. (4) The Rate.xlsx rule stays the default for every
money figure. An owner override such as "posted max" belongs to one run, is written in that run's state
doc, and is never copied into the answer bank unless the owner says so. (5) A run states any profile side
effect a site causes, once, in its close-out.
Consequences: Arc jobs are de-duplicated from `apply/log.csv`, not from the live site. Arc hides the
employer on its cards, so the log uses a per-job employer label and the employer-recency check never
matches across Arc jobs. Untested: whether Arc keeps the Applied list for long; the first dry check of a
new Arc layout is a manual read.

## ADR-048 · 2026-11-12 · "Relevant experience" and every free-text box is always drafted, shown in full and never left blank
Context: the batch-job-apply skill already cites this rule (owner statement, 11 Nov 2026); the log had no ADR for it.
Decision: "Relevant experience" and every other free-text box is always drafted from career-data and the CVs, checked against the answer bank, shown in full in the approval list, never left blank and never put to the owner as a question (Rui, 11 Nov 2026).
Consequences: the owner reviews the draft in the approval list rather than writing it; a draft that contradicts the bank is a CONFLICT (ADR-043), not a silent override.

## ADR-049 · 2026-11-12 · Apply run hygiene: site Applied list, gate-aware batching, ID numbers by hand, per-run ratings, direct merge of data log rows
Context: the Glassdoor and Arc runs of 11-12 Nov 2026 showed that Indeed's Applied list verified every Glassdoor submit, that staged forms and tabs were lost overnight, and that nothing covered ID-number fields or the merge path for log rows. The jsonl outcome record also lacked `ALREADY_APPLIED`, which `apply/log.csv` already had.
Decision: (a) The site's own Applied list is the de-dup and verification source (Indeed: myjobs.indeed.com/applied); site card tags prove nothing. An `ALREADY_APPLIED` outcome is verified by `site_applied_list` or `human`, never `confirmation_url`. (b) Gate-aware batching: staged forms and tabs do not survive idleness, so stage only while the owner is present and request every reCAPTCHA or Cloudflare clearance straight after approval; a smaller list is fine. (c) Government ID numbers (CPF, Documento, passport, tax ID, SSN) are typed by the owner only and are never echoed, logged or written to any file. (d) Per-run self-ratings that bundle skills are flagged and are per-run unless the owner says standing. (e) career-data apply-log rows may be merged directly by the run (owner authorised 12 Nov 2026); career-ai changes stay PR-only with owner merge.
Consequences: one status vocabulary, `applylog.APPLY_STATUSES`, feeds both records; `apply/log.csv` still accepts the six statuses it did (no STAGED or CLOSED). Amends ADR-045 and ADR-047.

## ADR-050 · 2026-11-12 · SmartRecruiters is a registered owner-run site; apply-log rows are written by the applylog CLI, never by hand
Context: the first SmartRecruiters run (InPost, 12 Nov 2026) applied through the oneclick-ui form in the owner's browser session. The form needs the résumé on page 1 before the screening questions appear, so the owner attaches the PDF and the run finishes and submits after approval. Success is a /success URL ("Application submitted!"). The close-out handed over a pipe-separated log row, which the log reader rejects.
Decision: (1) SmartRecruiters is `manual_channel`, status `registered`: owner-run, human-approved browser session only (ADR-038, ADR-040), no adapter, no harvesting. The public Posting API may be read for one posting the owner names (location, contract type, currency). (2) Its /success page counts as `confirmation_url`. (3) Runs write apply/log.csv rows and jsonl outcomes with `python -m jobscan.applylog upsert|outcome` and run `check` before a career-data PR. Hand-written rows are a fallback only when the CLI is unavailable, in the file's CSV format.
Consequences: one validated path into the log. Upsert keeps other lines byte-identical, so data PRs stay one-line diffs. Untested: SmartRecruiters forms from other employers (custom questions vary).

## ADR-051 · 2026-11-13 · The sdlc agent cannot read the checkout's .git; the agent/publish job split (i.H7) is deferred
Context: research on `anthropics/claude-code-action` at `6b6870e649b5ff408753befeaee5fc7989d4e6a9` showed that, before the agent starts, the action writes its token into `remote.origin.url` in `.git/config` (a write-scoped GitHub App token minted through OIDC), and that the agent's bare `Read`, `Grep` and `Glob` were not denied there. A probe with a fake token confirmed it on 11 Nov 2026: all three read `.git/config`. The agent has no network, `gh` or push tool, and the action revokes the app token when its step ends (`action.yml`, step "Revoke app token", only when no `github_token` is passed), so no exploit is known; but the agent could place the token in its own output, which `scan` only matches by pattern.
Decision: deny `Read(**/.git/**)` in `.claude/settings.json` and in `--disallowedTools` on both agent steps (a later stage checks out the issue branch, so the flag is the rule that always applies), and set `permissions.blockReadsOutsideWorkingDirectories` so the file tools stay inside the checkout. After the change the same probe: Read and Grep on `.git/config` denied, Glob returns nothing, `/etc/hostname` denied, `README.md` still readable. The two-job split (i.H7) stays optional and is deferred to before multi-user use. When it is done: `github_token: ${{ github.token }}` on a read-only agent job (no OIDC exchange, no `id-token`), one tarball uploaded with `archive: false`, a validator in the write job, about 20 tests rewritten.
Consequences: closes the one verified gap with a settings change and one flag. The OAuth token still sits in the `claude` process, and a deny rule is a pattern match, not a sandbox. Already-open agent branches keep their old settings file, but the workflow flag applies to them. `.claude/**` is on the protected list, so the agent cannot rewrite the rule. Untested: whether a future Claude Code version changes how `blockReadsOutsideWorkingDirectories` or the dot-directory deny matches; the tests pin the strings, not the behaviour, so repeat the probe after a Claude Code upgrade.

## ADR-052 · 2026-11-13 · The build report is copied aside before the reviewers run, and the build stage posts that copy first
Context: since the review step was added in PR #26, the build agent and the two review agents all write `.sdlc/comment.md`, and the review agents run in the same checkout after the build agent. Their text overwrote the build agent's report, so the issue comment for a build showed the review only: no summary of what was built and no fixed line saying the tests were not run by the agent (ADR-037).
Decision: a trusted step, before the review agents start, copies `.sdlc/comment.md` to `.sdlc/build-report.md`, or writes the fixed line "The build agent wrote no report." when there is none. The post step for stage `build` posts `build-report.md` (same 2500-character cap), then the existing **Review** block from `review.md`, the tests line and the next gate. Its blocked branch removes `build-report.md`, so no agent text is posted there. `build-report.md` joins `SDLC_OUTPUT`, so the secrets scan covers it, and the final scan runs after the copy. Other stages keep using `comment.md`. No prompt, allow-list, protected path or tool permission changes.
Consequences: the reviewers' `comment.md` is ignored for the build stage. The reviewers still have Write, so they could overwrite `build-report.md` as well; the final scan still checks what is posted, but the copy is not tamper-proof. Moving the copy outside the checkout would close that, and is the next step if it matters. The change takes effect after merge. The tests pin the step order, the copy and fallback, the post order and the blocked removal, not a GitHub run: verify on the next real `agent:build` run that the issue comment shows the build report, then the review.

## ADR-053 · 2026-11-13 · Greenhouse runs attach the CV with file_upload, close out in-session, and flag likely screen-outs
Context: the Greenhouse run of 11-13 Nov 2026 (Claude in Chrome) submitted 14 applications. Most CVs were attached with `file_upload`, so the 4-5 Nov hand-off was not needed. The close-out could not write apply/log.csv because career-data was cloned read-only. A question the skill's fallback bank already answered (on-call rotation) was asked. Honest "no experience" answers on three BVNK roles will probably screen them out.
Decision: (a) `file_upload` on the file-input ref is the default CV route in Claude in Chrome; the owner attaches and submits only after two failed uploads (amends ADR-045). (b) A run attaches career-data with push access at step 0 and merges its own apply-log-rows PR after `applylog check` passes (ADR-049(e)); career-ai changes stay PR-only with owner merge. (c) The answer search covers career-data, then the skill's fallback bank, the CVs, Rate.xlsx and the state doc before any question, and every question names the sources checked. (d) Where the bank and CVs support only "no experience", the run chooses that option, flags the job "likely screen-out", and still sends it; fit gaps are flags, not skips (ADR-029 stance). (e) Phone, city and address by job location from `location_rules` are decided (OPEN-QUESTIONS, 5 Nov), never an open question. (f) A prompt `WIDEN:` line allows up to 6 extra searches on the same site once the saved searches are exhausted; per run, never standing.
Consequences: one validated close-out path (`applylog batch`), ID numbers cannot enter the logs unnoticed, and the Greenhouse prompt no longer routes CVs to the owner by default. Untested: `file_upload` on forms other than the ones in this run; the BVNK screen-out is a prediction, not an observed rejection.

## ADR-054 · 2026-11-13 · Legacy SUBMITTED rows without a jsonl outcome are recorded with a reason; no verifier is invented
Context: `applylog check --strict` fails on 53 SUBMITTED rows (Glassdoor and Arc) written before the jsonl outcome record existed (ADR-045, ADR-050). Their verifier is unknown from the repository, so backfilling one would be a guess.
Decision: legacy SUBMITTED rows are listed in `apply/legacy-outcomes.csv` (`site,job_id,reason`) in career-data, with a reason and no invented date, verifier or employer. `check --data <dir> --strict` counts them as `legacy: N` and does not fail on them. A SUBMITTED row with no outcome and not on the list still fails `--strict`. A list entry that now has an outcome, or has no SUBMITTED row, is a warning and never an error. A job ID is printed only when it is already in the log.
Consequences: `--strict` fails on any new gap and passes on the agreed legacy set. Untested: whether the legacy set should later be backfilled from the sites' own Applied lists (ADR-049(a)); that would be a separate owner decision.

## ADR-055 · 2026-11-13 · Permission denials are named, and the stage agent's last message is shown when it wrote no report
Context: a build run logged only a count of permission denials, with no tool name, and the review agents' runs did the same. A first intent run ended "success" with no files written and a comment that said only "The agent produced no file changes.", so nobody could tell what the agent was refused or what it concluded. The action overwrites its execution file on every run, so the build agent's transcript was gone by the time the reviewers had run.
Decision: each agent step gets an id, and a trusted step after the agent's token reset copies the action's execution file to `.sdlc/exec-stage.json` (before the review agents start) or `.sdlc/exec-review.json`. The post step runs `jobscan.sdlc agent-notes` on the copies. It reads only the last `result` message and writes the number of denials and the distinct tool names per agent, with names sanitized to letters, digits and `_:().*-` and cut at 40 characters. If the stage agent wrote no report, it also writes that agent's final text, trimmed to 1500 characters, under the heading "untrusted, not reviewed", but only when the secrets and personal-data scan finds nothing in it. The job summary gets the counts line on every run. The issue comment gets the line only when something was denied. A blocked run posts none of this and removes the copies. No prompt, allow-list, protected path or tool permission changes.
Consequences: `tool_input`, which can hold commands and file content, is never read into any output. The layout of the execution file was not checked against the action's source from this session, so the parser accepts a JSON array, a single object or one object per line, and anything else reads as "none" rather than an error; repeat that check when the action is bumped. The review agents can write `.sdlc/`, as they can `review.md`, so the reviewers' copy, and the stage copy after the review runs, are not tamper-proof: the names are sanitized and the text scanned, but the counts are not authenticated. The change takes effect after merge. The tests pin the parser, the post step and the step order, not a GitHub run: verify on the next real agent run that the job summary names the denied tools.

## ADR-056 · 2026-11-13 · Apply runs: cross-site duplicate check, per-batch close-out, final click by ref, no autonomous mode
Context: the InPost double application: a LinkedIn Easy Apply submit (job 4476677792, SmartRecruiters behind it) and a SmartRecruiters URL the next day. The second run's dedup looked only at (site, job_id), and the first submit existed only in a project state doc. The same run saw Jobgether repost one role per country under new job IDs. Also: 11 LinkedIn submits went unlogged for two days; every LinkedIn Submit was clicked by coordinates because `find` returned nothing in the built-in browser; three jobs were submitted without an approval list after the owner wrote "submit all autonomous"; and a residence-country dropdown without Portugal (Ajaib, Workable).
Decision: (a) Before staging, a run checks employer and role across all sites with `applylog seen` AND every open project state doc. Aggregators get one application per role. (b) Apply-log rows are written and merged after each batch, not at the end of a run. (c) LinkedIn's "Application submitted" on the job page is verified_by `site_applied_list`. (d) The final Submit is clicked on a ref from `find`, or from `read_page` when `find` returns nothing. Never by coordinates or JavaScript; with no ref, the click is the owner's. (e) A chat word like "autonomous" never approves a submit and never creates an auto mode; ADR-042 auto mode stays deterministic code only. (f) A residence-country dropdown without Portugal, on a non-Thailand job, gets "Other" / "Not listed" and a flag. This supersedes the skill's old "choose Thailand" fallback.
Consequences: one more CLI call per candidate. The role normaliser can miss reworded titles, so the run still reads the state docs. Untested: read_page refs on LinkedIn dialogs in the built-in browser.

## ADR-057 · 2026-11-13 · A stage whose output is already on the branch is skipped; workflow hygiene (i.F3-i.F7)
Context: opening an issue runs `intent`, and a later `agent:intent` label ran it again (#44, #67, #70): a wasted agent run and a second comment. The checkout step ignored `stop`, so after a budget stop it could overwrite the budget message. A stopped run printed "Next gate" and named the next label. The stage-ended message told no one what to do. The pinned actions ran on Node 20, and `ubuntu-latest` was moving to Ubuntu 26.04. The `pytest` check on agent PRs depends on a dispatched run that no ruleset requires yet.
Decision: (a) a trusted helper, `jobscan.sdlc skipped`, reads the single file a stage writes (`intent`, `spec`, `plan` only) on the checked-out branch. When it exists, the run starts no agent, posts one line and removes only the trigger label: no `stage:*` label, no next gate. Build, review, release and support are never skipped. (b) The checkout respects `stop`. (c) A stopped run prints no next gate. (d) The stage-ended wording says to open the run log, where the agent's last message is shown when readable. (e) `actions/checkout@v7` and `actions/setup-python@v7` (Node 24). (f) Every workflow pins `runs-on: ubuntu-24.04`. (g) The `pytest` check: no code change. The dispatched run's check run is the one the PR relies on, and no ruleset requires it. The `pull_request` run for the same SHA concluded `failure` with no jobs and creates no check. Adding the required check is a repository setting, a human step.
Consequences: a redo needs the owner to delete the file on the branch before the label. Two agent labels in one second still run one after the other. Workflow behaviour is verified only by tests (`tests/test_sdlc_skip.py`, `tests/test_sdlc_concurrency.py`, and the post step run under a fake `gh`) until the throwaway chain runs: verify on a throwaway chain that an intent with the file present posts only the skip line, that a stopped spec posts no next gate, and that the pinned runner and actions run. Unverified: GitHub's docs on bot-triggered PR approval and on required-check matching (docs.github.com did not resolve here); the `persist-credentials: false` behaviour of checkout v7 (whether it still writes the token into `.git/config`); the Node 24 major tags were read from the releases pages and `action.yml`, not run.

## ADR-058 · 2026-11-13 · The pre-agent helpers run from trusted code, and the sdlc package is protected (i.F9)
Context: After "Check out the issue's branch" the working tree is the issue's branch, which an agent wrote. The skip step and the two commands of the frame step ran `PYTHONPATH=src`, so a later stage imported code an agent had written on the branch (`src/**` is in the build stage's writes). That code wrote `.sdlc/prompt.md` for the next agent and the skip comment, which is posted without a scan. No token was in those steps and a human reviews the diff before merge, so the exposure was small, but it defeated ADR-036.
Decision: (a) a trusted load of `src` at the trigger commit, the same sparse checkout as the post-agent load, runs right after the branch checkout and before the skip step. The skip, issue and prompt commands run as `PYTHONPATH="$TRUSTED_SRC" python -P -m jobscan.sdlc`; the helpers import only the standard library and their own package, so the sparse checkout is enough. (b) `src/jobscan/sdlc/**` joins `PROTECTED`, so `check` refuses an agent change to the package in every stage. The build stage's `src/**` write pattern still matches it; protection is checked first.
Consequences: the helpers no longer run code from the branch; the decide and budget steps still run from the trigger commit, as before. The sdlc package can be changed only by a human PR. This takes effect after the PR is merged to main, because the workflow runs from main's file. Workflow behaviour is verified only by tests (`tests/test_sdlc_trusted_code.py`, which runs the skip and frame steps through bash with TRUSTED_SRC set, and `tests/test_sdlc.py`) until a throwaway issue runs: verify on it that the step log shows TRUSTED_SRC set for the skip, frame and prompt steps, and that the pre-agent load runs before the skip step.

## ADR-059 · 2026-11-19 · The bot PR body no longer has a tests-green box (i.F8)
Context: The draft PR body from `jobscan.sdlc` had a `- [ ] tests green` checkbox. The required `pytest` check is the proof that the tests pass, and the box duplicated it.
Decision: Remove the tests-green box from the PR body and keep the other four (intent accepted, spec approved, plan approved, review findings resolved). The release prompt names the required `pytest` check green on the head commit instead of "tests green".
Consequences: The required `pytest` check is the only automatic test gate. Agent PRs need one approval click per run to report it (ADR-057 notes this).

## ADR-060 · 2026-11-19 · The sdlc engine's values move to a config file (S1 B)
Context: The engine's project values were hard-coded in `src/jobscan/sdlc/` and copied into `sdlc.yml` and `tests.yml`: the trusted author associations, the label-to-stage map, each stage's roles, outputs and turn limit, the protected paths, the size limits, the budget caps, the agent branch prefix, the model, the runner and the git identity. Changing one meant editing several files, and nothing checked that the copies agreed.
Decision: The values move to `.github/sdlc-config.json`, a protected path (`.github/**`). The trusted checkouts (ADR-036) fetch it from the trigger commit, sparse with `src`, and every engine call reads it with `--config`. decide and budget run before the trusted copy exists, so they read the file from the trigger commit's workspace. The built-in constants stay in the engine as the fallback when the file is absent. A file that is present but malformed raises an error, and the run stops; nothing falls back silently. Values only the workflow YAML can hold (runner, model, Python version, titles, git identity) stay in the workflow text, because YAML cannot read JSON; `tests/test_sdlc_config_file.py` keeps them equal to the file.
Consequences: A config change is a human PR, like any change under `.github/`; no agent can write it. The file takes effect when merged to main, because the workflow runs from main's file. A malformed file stops every stage. An absent file falls back to the built-in values without an alarm, so the tests keep the two equal. The trusted copy now also holds `.github/`, read only. This PR changes no behaviour: the file holds exactly the built-in values.

## ADR-061 · 2026-11-20 · Apply-run prompts take identity from career-data only; close-out per batch with csv/jsonl parity
Context: the 18-20 Nov Greenhouse run needed a conflict fix in `apply/log.csv` (CR line endings and conflict markers pushed once), a jsonl line added after the merge (ília 6261726004), and a replacement PR for unrelated histories. The run prompts carried phone numbers copied from the bank, and the Greenhouse prompt asked for a read-only career-data clone, which made the per-batch close-out impossible.
Decision: (a) Run prompts hold no phone, address or other identity value; they come only from career-data `location_rules` by the job's location (ADR-046). (b) Every site prompt clones career-data with push access at step 0 and merges its own apply-log PR by REST once `applylog check --strict` is green. (c) After each batch the run writes the csv rows and the matching jsonl lines and checks parity both ways. `applylog check` now also fails on CR line endings and conflict markers in `log.csv` and warns on a jsonl outcome with no log row. (d) The next ADR number is read from `docs/DECISIONS.md` in the repo at the time, never assumed. (e) A prompt-improvement run backs up each prompt file before overwriting it and replaces its own `.Improve.txt`.
Consequences: Prompts are shorter and cannot drift from career-data. Close-out is slightly longer per batch. The reverse-parity check is a warning, not an error, because older logs hold outcomes with no row; promote it to an error once those are cleaned. Untested: the REST merge route when GitHub's mergeable state stays null (retry after a few seconds).

## ADR-062 · 2026-11-20 · Apply runs reconcile the site's Applied list with the log before closing; USD when a form states no currency
Context: the LinkedIn run of 18-20 Nov submitted 25 jobs, all logged and checked against LinkedIn's Applied tab at 20/20 and 4/4. The next morning the Applied tab (count 1,072 at the last submit, 1,074 later) held two entries that are in no log row and that the run did not submit: KLx Tech Lead (Lisbon) and EPAM Senior Software Engineer (Singapore). Nothing in the repository could say who submitted them, so the run could neither log them nor call the log complete. In the same run the answer bank lacked a rule for a salary field that names no currency (the owner said "USD always", 19 Nov), `jobscan` was not installed in the session so the rows were appended by hand, `gh pr create` was refused (REST works), and a state doc was archived under a name an earlier archive already held.
Decision: (a) `python -m jobscan.applylog reconcile --log apply/log.csv --file <applied.csv>` reads a CSV of the site's Applied list (header `employer,role`, extra columns ignored), matches each entry with `seen` (employer and normalised role, any site, APPLIED statuses only) and prints the entries no row covers; exit 1 when there are any, 2 on a bad file. (b) A run reads the site's Applied list at its start and again before it closes, runs `reconcile`, and reports every uncovered entry once. It never logs one as SUBMITTED on its own: the owner says whether he submitted it (then `verified_by` is `human`) or whether it needs investigating. (c) A form field that names no currency takes the USD figure from Rate.xlsx; a per-run figure the owner gives for a field the bank has no entry for (current salary) stays per-run. (d) Runs attach career-ai at step 0 and call the CLI with `PYTHONPATH=src`; if it cannot be installed, the run writes the csv row and the sorted-key jsonl line by hand, validates both, and says so. (e) A closed run's state doc is archived under a name no earlier archive holds (`apply-state-<site>-<last date>.md`, with `-2` if taken).
Consequences: one more CLI call at the start and end of a run, and one more page to read. The check proves a gap, not its cause: an entry can be the owner's own submit, another session's, or an application whose title the site rewrote (the match uses the normalised title, so a reworded one shows as a gap and is reported, not logged). `reconcile` is read-only. Untested: reading LinkedIn's Applied tab at 1,000+ entries (the tab pages ten at a time; the run reads the first pages only, so an older gap is not found); the run takes the newest entries back to the previous run's last row.

## ADR-063 · 2026-11-20 · Glassdoor run lessons: strict check before every merge, per-job answers stay per-job, ID fields are hand-offs, fresh tab after a freeze
Context: the Glassdoor run of 18-20 Nov (Indeed smartapply behind Easy Apply, Claude in Chrome) submitted 8 jobs, skipped 3 and blocked 1. Slips and near-misses: (1) the close-out ran `applylog check` without `--strict`; run strictly afterwards, it showed `apply/log.csv` on main held 137 CRLF lines among LF ones (rows from earlier runs), so every later strict check failed and nothing had noticed; (2) two Cielo rows were logged with `verified_by` `site_applied_list` although the Indeed post-apply page had been reached (that page counts as `confirmation_url`); (3) a per-job answer (Documento "N/A", disability "Não") was pre-set on the next job of the same employer without being listed, caught only by the approval list; (4) a mandatory Documento field needed the owner's ID handling mid-run; (5) the Indeed tab froze or vanished after a reCAPTCHA clearance, and the Applied list, not a retry, settled what had been sent; (6) a custom select picked a hidden option; (7) role titles with commas and pipes need a CSV writer, not string joins.
Decision: (a) Every close-out runs `applylog check --strict` and the career-data PR is merged only when it prints `ok`; a plain `check` does not close a batch. (b) `apply/log.csv` is LF only; CRLF is a check failure and is fixed in the same PR that finds it. (c) `verified_by` is `confirmation_url` when the run reached the site's post-apply or confirmation page, `site_applied_list` when it only saw the job on the Applied list. (d) A per-job answer the owner gives is used on that job only; the next job, even at the same employer, lists the answer again for confirmation. (e) A required ID field (CPF, Documento, passport, tax ID) is a hand-off before the job goes on a list: the run stages the rest, names the tab and field and says "Documento present" or "empty". (f) After a frozen or vanished tab: `tabs_context_mcp` with createIfEmpty, a fresh tab, and a read of the site's Applied list before any retry. (g) Custom selects: choose only visible options (width above 0) and read the value back. (h) Titles with commas, quotes or pipes are written with a CSV writer. (i) Every SKIPPED or BLOCKED candidate is logged at its batch's close-out, not at the end of the run. (j) After a list, "YES" covers that list only; "finish" with no list on screen means close out and archive, stage nothing new.
Consequences: no code change: `check --strict` already rejects CR line endings and `reconcile` already exists (ADR-062); the lessons live in the prompts, the skill and the data fix (career-data PR normalising `apply/log.csv` to LF and correcting two `verified_by` values). One more strict check per batch. Untested: whether other editors or the Drive-side tooling reintroduce CRLF; `check --strict` will say.

## ADR-064 · 2026-11-20 · The sdlc engine is its own package, sdlc_engine (S1 C)
Context: the sdlc engine lived at `src/jobscan/sdlc/`, imported and named `jobscan` throughout, and the workflow ran `python -m jobscan.sdlc`. So a second project could not reuse the engine without taking the whole jobscan package with it, and the engine's own names said the engine was jobscan's.
Decision: the engine is the top-level package `sdlc_engine` (`src/sdlc_engine/`), with the same modules and functions as before. The workflow's sdlc steps, the protected path in `.github/sdlc-config.json` and in `PROTECTED`, the tests and `docs/SDLC.md` name `sdlc_engine`. The engine's code no longer imports `jobscan`, and only one prompt string still names it (see Consequences); the jobscan distribution and its scripts are unchanged.
Consequences: behaviour is unchanged; the workflow and the tests name `sdlc_engine`, and a second project can depend on the engine and supply only `.github/sdlc-config.json`. Still named `jobscan` for now: the trusted-code step names in `sdlc.yml` (`Trusted jobscan code ...`, which the ADR-036 tests match by name), and the agent's first-line support prompt, which points at `src/jobscan/apply/faillog.py` and `python -m jobscan.apply bundle`. Those are follow-ups that need the owner's decision, because the prompt text changes what the agent reads. Past ADRs keep their original wording.

## ADR-065 · 2026-11-20 · Project-specific prompt text, owner handle and secret pattern move from the engine to the protected config (S1 D)
Context: after ADR-064 the engine imported no project, but its prompts still carried career-ai's sentences (the files a stage must never touch, the docs it reads first, the support sources and the bundle command), the blocked budget comment carried the owner's handle, and the built-in credential list carried one project's key. A second project would inherit all of it.
Decision: those values move to the optional `prompt` object and the `budget.mention` key of `.github/sdlc-config.json`. The built-in defaults are generic: no never-touch sentence, read-first list `CLAUDE.md` and `docs/SDLC.md`, support sources "README.md and docs/", no bundle clause, no handle, no extra credential pattern. A malformed or wrongly typed value raises `ConfigError`; a missing `--config` uses the generic defaults; a `--config` path that names no file still raises. The files in `tests/golden/` hold the rendered prompts of every stage and the blocked comment, and the tests keep them byte for byte equal to what career-ai's config renders.
Consequences: a second project supplies its own prompt block and handle in its own config, and the engine needs no change. The config is a human-PR-only file (protected path). This supersedes the follow-up named in ADR-064's consequences for the prompt text, the handle and the credential pattern; the trusted-code step names are renamed to "Trusted engine code" in the same PR. Still named for a decision: the built-in protected-path defaults (`**/profile.yaml`, `**/authorization*.yaml`) in `src/sdlc_engine/`, which stay as a fail-closed safety list when no config is given.

## ADR-066 · 2026-11-20 · The sdlc workflow is a thin caller around a reusable stage workflow (S2)
Context: `sdlc.yml` was one file of about 500 lines, and its single `stage` job held every step. The next step extracts the engine, and a second project should be able to run the same stage steps without copying them.
Decision: `.github/workflows/sdlc.yml` is a thin caller. It owns the name `sdlc`, the triggers (unchanged), the concurrency group (unchanged), the top-level `permissions: {}`, the job-level permissions the stage needs, and one job `stage` that calls `./.github/workflows/sdlc-stage.yml` and passes `CLAUDE_CODE_OAUTH_TOKEN` by name. The job-level `if` (ADR-039) stays on the caller, because a skipped caller job never starts the called workflow. `.github/workflows/sdlc-stage.yml` declares `workflow_call` with that secret and holds the `stage` job: its runner, its 30-minute timeout, its permissions, its job `env` and all 31 steps, copied unchanged and pinned by `tests/golden/sdlc-steps.txt`.
Not verified: this session could not reach docs.github.com (the proxy refused it), so the rules below come from the workflow files' own use, not from the docs. A reviewer must check the reusable-workflows page before this merges: which job-level keys a calling job may set (`uses`, `with`, `secrets`, `permissions`, `concurrency`, `needs`, `if`, `name`, and whether `timeout-minutes` is allowed); whether a called job's permissions are capped by the caller's job permissions; and what `github.event`, `github.sha`, `github.ref`, `github.run_id` and `github.workflow_ref` resolve to inside a called workflow. The stage job keeps `timeout-minutes: 30` in case the caller may not set it.
Consequences: a second project can call the same stage workflow with its own secret. The budget gate still counts the caller's runs, because it queries `actions/workflows/sdlc.yml/runs` and the caller keeps the name. The steps keep the trigger commit's `github.sha` only if the docs confirm that a called workflow sees the caller's context. Top-level permissions stay `{}`, so the grants are per job, and `tests/test_sdlc_config.py` pins that. The stage workflow is a protected path (`.github/**`).

## ADR-067 · 2026-11-23 · Structured review output, a computed risk tier and a drop rule for findings (m2)
Context: the review stage's two real reviews (issues #44 and #79, PR #45 and #80) showed four problems. Each heading said "No finding", so a clean review was long. The verdict was a free-text line near the end, so the workflow could not read it. Findings cited `file:line` but nothing checked the line was in the diff. On #79 all three nits were remarks about wording in stage documents under `docs/intents/`, not code or behaviour. The source the task names, Anthropic's "Solving code review", was not found in this session. Only secondary pages about Anthropic's code-review work were read (the "How the Claude Code team does code review" write-up and coverage of the March 2026 Code Review launch). Nothing below depends on claims from those pages.
Decision: (1) `REVIEW.md` says, per area, what failure looks like (docs: it lies; workflow and config: it misroutes; sdlc code: it leaks or posts unscanned text; tests: it passes without checking), requires a `file:line` from the diff for every IMPORTANT or NIT, allows at most three nits, checks `docs/intents/` for statements false about the diff and not for wording, names the class of a bug, and tags pre-existing problems separately. (2) The review file has a fixed shape: line 1 is `Nothing to fix.` or the count line; then one `IMPORTANT|NIT|PRE-EXISTING path:line - text` per finding, `line` a number or a range; an optional `Checks:` last. The engine's parser (`src/sdlc_engine/review.py`, pure, no `eval`, lines at most 300 characters, at most 50 findings, at most 20 000 bytes) reads it. Anything malformed, a count line that disagrees with the findings included, fails closed as one IMPORTANT `unparseable review`. (3) Without a model call, an IMPORTANT or NIT whose line is not inside a hunk's new-side range of `.sdlc/diff.patch` (changed lines and their context) is dropped and listed in the run summary by tag and line. PRE-EXISTING is exempt. A range is kept when any of its lines is in a hunk. (4) The posted `Checks:` line is the first line of the check results read by a trusted step, passed as a step output, not read back from `.sdlc/checks.txt`, because the reviewers may write files. (5) The risk tier (HIGH, MEDIUM, LOW) is computed from the changed paths against the protected paths in `.github/sdlc-config.json`, never from the author, and goes in the PR body with a Testing, a Risk and a How to revert section. (6) `needs_changes` (a kept IMPORTANT) chooses only the wording of the Next gate line. It ticks no box, adds no label and blocks nothing.
Adopted from the write-up, as design principles rather than product claims: findings must point at the change, and the output is structured so a machine can read it. Left out: a fan-out of parallel review subagents with a separate verification pass per finding. Reason: each review would multiply model usage, and this owner is on the Pro plan, with usage limits. The stage keeps one reviewer and one security-reviewer pass, read directly for a small diff, as before (the review stage does not force subagents).
Tuned on two real reviews, #44 and #79: the new prompt was written against them, and their text is kept as regression fixtures in `tests/fixtures/sdlc-review/` (the old text must fail closed; a new-format conversion must parse with nothing to fix).
Not verified: nothing has run on GitHub. The workflow change (the post step calls `review`, and the checks steps have ids and write a step output) is not exercised by any real run; `tests/test_sdlc_config.py` and `tests/test_sdlc_review.py` run the post step on fixtures only. The `Checks:` line carries the commit id on a successful read, so it shows no pass or fail until the first real run confirms the layout; a follow-up should quote the `pytest` line instead.
Consequences: `REVIEW.md`, `docs/SDLC.md`, `.github/workflows/sdlc-stage.yml` and `docs/DECISIONS.md` are protected paths, so this change needs the owner's review and a human merge. The review prompt and the post step changed; `tests/golden/prompt-review.md` and `tests/golden/sdlc-steps.txt` are regenerated by their generators.

Follow-up on the same ADR: a dropped IMPORTANT is now visible in the posted review as one counts-only line (`Dropped (not on a changed line): I important, M nit. See the run summary.`, before `Checks:`), and the Next gate never says "No Important finding" when an IMPORTANT was dropped; it says how many were kept out and that a human decides. The line limit for a whole finding line rose from 300 to 600 characters (the prompt still asks for under 300; the #79 nit is about 220); the input cap fell to 19 000 bytes so the posted review stays under the workflow's 20 000-byte display limit. `needs_changes` is unchanged. Accepted residuals: `.sdlc/diff.patch` is written by a trusted step, but the reviewers may write files, so a forged diff could only hide that reviewer's own findings, never add one that is not in the real change; the `Checks:` line quotes the first line of the check results, which on a successful read is the `commit: <sha>` line, so pass or fail is on the next line, and the existing tests note (`Tests were NOT run ... The pytest check on the PR is the evidence`) remains the pointer to the pytest check.

## ADR-068 · 2026-11-23 · Review round cap, diff-only re-review from round 3 and an optional verifier (m4)
Context: every pushed build is reviewed, and each review costs Pro usage (ADR-030, ADR-032). An agent loop (build, review, build again) could re-review the same code many times on one issue, and each later review re-read the whole branch. The review's IMPORTANT findings were also posted without a second look, so a finding the code already guarded could block the next gate.
Decision: (1) Each posted review carries a hidden marker, `<!-- sdlc-review round=N sha=<sha> -->`, written by trusted code in the post step, only when a review agent ran. The round is one more than the markers in the issue's comments written by the workflow's own bot (`github-actions[bot]`). A marker in any other comment is ignored, because anyone can comment on a public issue. (2) `SDLC_MAX_REVIEW_ROUNDS`, a repository variable read the way the budget gate reads its variables, caps the rounds: unset or not a whole number means 3, and 0 blocks every review. A review runs while round <= cap. A blocked round runs no review agent, posts one short comment that starts with the owner's mention from `budget.mention` in `.github/sdlc-config.json` (the engine names no handle), keeps the job green and adds a warning annotation. The budget gate still runs first. (3) From round 3 the review reads `git diff <last reviewed sha>...HEAD`, while that sha is an ancestor of HEAD; otherwise it reads the full diff and the step summary says so. The drop rule reads the same `.sdlc/diff.patch` the reviewer saw. The earlier findings, taken from the counted bot comments, go into the prompt as untrusted data, scanned and fenced, with the instruction not to repeat them. (4) An optional verifier runs only when `SDLC_REVIEW_VERIFY` is exactly `true`. It is a second read-only agent (Read, Grep, Glob; 8 turns; the reviewers' pin, permissions and disallowed tools). Trusted code builds its prompt from the IMPORTANT findings the review keeps and the diff, both framed as untrusted. Only a CONFIRMED finding is posted; a DROPPED one is named in the step summary by tag and line only. A missing or malformed answer keeps every finding. The verifier is off by default because it is one more model call on every review that has an IMPORTANT finding, on a plan with usage limits.
Placement: the verifier's agent step comes after the reviewers' token reset and trusted reload, not directly after the reviewers' agent. Its prompt is built by engine code, and the reviewers can write the workspace, where `trusted/` lives, so the reload taken after them is the only copy that is not theirs. The verifier therefore has its own token reset after it and a read of its execution file, and the reviewers' execution file is copied before the verifier can overwrite it.
Also decided: the round count reads the issue's comments fetched after the build agent ran, in the post-push token step that already reads the check results (ADR-037). The build agent can write `.sdlc/`, so a comment history fetched before it could be forged. A failed read blocks the review (fail closed). Agent text may not contain a round marker: the scan withholds it, so a build report cannot count as a round or give a false base. The `review` stage (a label applied by hand) is not counted and not capped: it is not part of the automatic loop.
Not verified: nothing has run on GitHub. The workflow steps, the cap, the diff base and the verifier are tested on fixtures and on a temporary git repository (`tests/test_sdlc_rounds.py`, `tests/test_sdlc_verifier.py`, `tests/test_sdlc_verifier_steps.py`); no real run has counted a round, read a bot comment or started the verifier.
Residual risks: (a) a person with write access can delete a bot's comment, which lowers the count: the cap then allows more rounds, and that is the owner's own action. (b) The reviewers can write `.sdlc/review.md` and `.sdlc/diff.patch` (as ADR-067 accepted), so a forged diff could hide a reviewer's own findings. (c) The verifier is a model: a wrong DROPPED removes a real IMPORTANT finding from the posted review, and the summary names only tag and line; a human sees that only in the run summary. (d) From round 3 the reviewer sees only the change since the last reviewed commit, so a problem in an earlier round's lines is seen only by a full read at merge time. (e) The verifier reads the same workspace the reviewers could write, so its answer is as trusted as the reviewers' own output: it can drop findings but cannot add any.
Consequences: `docs/SDLC.md` (the review section), `docs/DECISIONS.md`, `.github/workflows/sdlc-stage.yml` and `src/sdlc_engine/` are protected paths, so this change needs a human merge. The review prompt and the stage steps changed: `tests/golden/prompt-review.md` and `tests/golden/sdlc-steps.txt` are regenerated by their generators; no other golden file changed. The repository variables are optional: with neither set, the cap is 3 and the verifier is off.
Follow-up on the same ADR: a finding the verifier drops is now announced in the posted review by a counts-only `Dropped by the verifier (not confirmed): I important.` line, the first line is never `Nothing to fix.` when the verifier dropped anything, and `dropped_important` counts diff and verifier drops together, so the Next gate names the drop in a sentence that is true for either kind; a test that asserted `Nothing to fix.` after a verifier drop now asserts the new first line.

## ADR-069 · 2026-11-24 · Rui-only data lives under profiles/<id>/ in career-data
Context: the answer bank, standing-answer files, triage keywords, rate card, CV manifest and open questions sat at career-data's root or in shared folders, although they describe one person. Profiles already live in profiles/<id>/ (config.py, folder name = id). A second user would need a second root copy of every file.
Decision: (a) every file that describes one person moves under profiles/<id>/ (phase A: answer_bank.yaml, apply/answer-bank.yaml, apply/triage.yaml, rate_card.json, cv_manifest.json, OPEN-QUESTIONS.md; phase B, when no run is open: apply/log.csv, legacy-outcomes.csv, logs/apply, logs/runs.jsonl, applications/). (b) src/jobscan/layout.py resolves the path: profiles/<id>/ first, legacy root path as a fallback until the data PR merges, then the fallback is removed. (c) The profile id defaults to the only profile and must be given with --profile when there are several. (d) authorization.yaml, config.yaml, scan state and reports stay at the root until the multi-user data model is decided. (e) Rate.xlsx and the CV PDFs stay in Drive.
Consequences: code ships before data (ADR-063); the data PR is renames only. Run prompts, the batch-job-apply skill and the project instructions must be updated after the data PR. Untested: the cloud routine's publish step against the new layout (it publishes reports/ and state/, which do not move).

## ADR-070 · 2026-11-24 · The legacy root-path fallback for profile files is removed
Context: ADR-069 (b) let code read Rui-only files from the data root until the data PR merged, so that code could ship before data (ADR-063). The data PR (career-data #64) has merged.
Decision: layout.resolve returns profiles/<id>/<name> only. A data repo with no profile folder, or several without --profile, is a ConfigError. A missing file is reported by its new path. Supersedes ADR-069 (b) for the fallback; (a), (c), (d) and (e) stand. Phase B (apply log, logs, applications) is unchanged.
Consequences: a checkout of career-data from before #64 no longer works with this code. Tests that wrote files at the data root now write them under profiles/<id>/. Run prompts, the batch-job-apply skill and the project instructions must name the new paths. Untested: cv-check still reports the four CV PDFs as missing because they live in Drive (unchanged from before ADR-069).

## ADR-071 · 2026-11-24 · Apply-run records move under profiles/<id>/; the application queue stays at the root for now
Context: ADR-069 (a) listed phase B. apply/log.csv, apply/legacy-outcomes.csv and logs/apply/*.jsonl are written only by owner-run browser sessions (ADR-061). applications/queue.json and logs/ are in pipeline.PUBLISH_PATHS, so the scan routine commits them, and career-data's README says the routine never pushes profiles/.
Decision: (a) the three apply-run records move to profiles/<id>/apply/log.csv, profiles/<id>/apply/legacy-outcomes.csv and profiles/<id>/logs/apply/. (b) layout.resolve reads the root path of a name in LEGACY until the data PR merges: the profile path wins when it exists, a root path that exists is used as it is (so a file's history stays in one place), and a name that exists nowhere is created at the profile path. A cleanup PR then removes LEGACY, as ADR-070 did for phase A. (c) applications/queue.json, applications/answers.json and logs/runs.jsonl stay where they are until the owner decides whether the scan routine may commit under profiles/. The failure lines the apply run writes to logs/apply/ (apply/faillog.py) also stay at the root: one run covers several profiles, so no single profile owns them. (d) the applylog CLI takes the log from --data and --profile when --log is omitted, and still accepts an explicit --log, relative to the cwd as before.
Consequences: run prompts, the batch-job-apply skill and the project instructions name the new log paths after the data PR. The strict check must pass on both layouts during the transition. Until the owner moves the failure lines, logs/apply/ in a data repo holds both the failure lines (root) and, after the data PR, the outcome lines (profile); a cleanup PR must not treat the root folder as only legacy.
Acceptance: pytest passes (including test_no_personal_data.py). Against the career-data checkout as it was at ADR-071, `python -m jobscan.applylog check --strict --data <path> --log <path>/apply/log.csv` and the same command without --log both print ok with the same row count (164) and legacy count (53).

## ADR-072 · 2026-11-24 · The legacy root-path fallback for apply-run records is removed
Context: ADR-071 let code read apply/log.csv, apply/legacy-outcomes.csv and logs/apply/ from the data root until the data PR moved them. The data PR (career-data #65, e7de612) has merged.
Decision: layout.resolve returns profiles/<id>/<name> only; LEGACY is removed. apply_path keeps the root location for a data repo with no profile folder. applications/, logs/runs.jsonl and the failure lines that apply/faillog.py writes to the root logs/apply/ stay at the root (ADR-071 (c)). Supersedes ADR-071 (b); (a), (c) and (d) stand.
Consequences: a checkout of career-data from before #65 no longer works with this code. Run prompts, the batch-job-apply skill and the project instructions must name profiles/rui/apply/log.csv and profiles/rui/logs/apply/ (done separately, not in this PR). Untested: moving the failure lines and the queue; both need the owner's decision on whether the scan routine may commit under profiles/.

## ADR-073 · 2026-11-25 · Stage agents run their subagents in the foreground (#118)
Context: two intent runs on #118 ended without writing `intent.md`. Each agent said it was waiting for a subagent (the stakeholder, then its notification) and ended its turn after 35 to 39 seconds, with no file changes. Claude Code starts a subagent that the main conversation spawns in the background by default (the sub-agents page), and the stage ends with its turn, so the work still running is lost. Intent runs on 20 and 23 November worked with the same prompts and workflow. On #110 the agent spawned no subagents; on #118 it did. The env-vars page lists `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`: set to `1`, it removes the background parameter from the Bash and subagent tools and stops Claude backgrounding subagents. Bug reports say it is ignored for several subagents at once and for fork subagents, so it is not proven to cover every spawn. Read from the docs' summary text; the page was not read in full.
Decision: (1) Each `anthropics/claude-code-action` step (the stage agents, the review agents and the verifier) sets `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` to `"1"`. This is the guard. (2) The shared stage prompt tells every stage to run each subagent in the foreground, one at a time, to wait for its result, and, if a subagent returns nothing, to write that role's part itself. This is the second layer: a run still works where the setting does not reach a subagent. Nothing else in the workflow changes: no permission, trigger, tool list, model, token or step order. `tests/test_sdlc_foreground.py` pins both layers, and the prompt and step goldens are regenerated by their generators.
Consequences: agents cannot run background commands or background subagents. This does not change who may merge: the stage still opens a draft PR, a human merges, and no stage gains a token, a tool or a permission. A stage with several subagents runs them one after another, so it takes longer; the turn caps in `.github/sdlc-config.json` still bound it. Not verified: no real run has happened yet. The canary is a real intent run on #118: it must write `intent.md` with the stakeholder and product-owner parts. If it still ends early, the next candidate is `CLAUDE_CODE_FORK_SUBAGENT=0`, which is a separate decision and is not made here.

## ADR-074 · 2026-11-25 · The spec stage's turn budget is 20 (#118)
Context: the spec stage on #118 failed twice with "Claude reported a successful result after N turns, exceeding the configured maximum of 12": once at 19 turns and once at 14. The workflow then discarded `spec.md`. ADR-073 had already fixed the intent stage's foreground subagents; the spec stage's cap was still 12.
Decision: `stages.spec.turns` in `.github/sdlc-config.json` goes from 12 to 20, and the built-in `"spec"` turns in `src/sdlc_engine/__init__.py` go to 20 too, so `tests/test_sdlc_config_file.py` (which keeps the file equal to the built-in values) still passes. No other stage changes: intent stays at 12, plan 15, build 40, review 15, release 10, the support stages 10, 15 and 20.
Consequences: a larger spec costs more tokens per run, and a spec run may take up to 20 turns before it is stopped. The intent stage and the others are unchanged. If a stage still overruns, split the stage; do not raise the limit again without a decision. `.github/` and `src/sdlc_engine/` are protected paths, so this change needs a human merge. Not verified: no real spec run on #118 has happened since the change.

## ADR-075 · 2026-11-25 · All owner-specific data in the data repo moves under profiles/<id>/ (issue #118)
Context: ADR-069 to ADR-072 moved the answer bank, the apply log and the other standing files under profiles/<id>/. The application queue, reports, scan state, answers, apply-run history, failure lines, the apply section of config.yaml and authorization.yaml still sit at the data root. A second user would share or duplicate them, and ADR-069 (d), ADR-071 (c) and ADR-072 kept them there until the owner decided whether the scan routine may commit under profiles/.
Decision: (a) every file above moves to profiles/<id>/ at the same relative name; budgets, sources, blacklist and manual_channels stay in the root config.yaml. (b) The scan routine may commit under profiles/<id>/ through an explicit allowlist only: reports, state and applications/queue.json (never profiles/ as a whole, never logs/, answers.json or any identity file). While LEGACY exists the allowlist also names the three root paths. The staged-path check in pipeline guards pipeline's own bugs and is not an enforcement boundary; a server-side control in career-data is a follow-up. (c) LEGACY resolves by folder for reports, state and applications, reads and writes where it reads (ADR-071 (b)), and is removed in a cleanup PR. (d) authorization.yaml moves last, in its own career-ai and career-data PRs, with no fallback: missing means inactive and the scan stops, and a stale root copy makes the code refuse to run and is never read. (e) Failure lines go under the profile of the failed job from the queue row; a failure with no row is skipped with a warning. (f) State is per profile, including the API budget and the seen-set. Supersedes ADR-069 (d), ADR-071 (c), the "stay at the root" line of ADR-072 and the data README rule that the routine never pushes profiles/.
Consequences: a data repo with no profile folder is no longer supported for the moved files (as ADR-070). The scan routine is paused while the data PR is open and for the authorization step; no browser-apply run between the data PR and the cleanup PR. applications/answers.json and logs/runs.jsonl are created on first use of apply questions and apply run; scan run history is state/runs.jsonl. decide gets --profile and decide.yml changes in the data PR. Run prompts, the batch-job-apply skill and the project instructions name the new paths afterwards. Untested: the server-side control (rulesets, CODEOWNERS or a CI check) is not confirmed for this repo.

## ADR-076 · 2026-11-25 · The build stage's turn budget is 60 (#118)
Context: build runs on #118 used more turns than the build cap of 40. Run 45546171417 hit `error_max_turns` at 41 turns. Run 45548231929 reported a successful result after 47 turns, and the action failed the step with "Claude reported a successful result after 47 turns, exceeding the configured maximum of 40". The check, commit and push steps were skipped, so nothing reached the branch. The scoped slice (plan tasks 2 and 3) is a normal build slice; the first run finished 3 tasks in 27 turns, so the work itself fits. The action enforces the cap after the fact, so a run that overshoots loses its finished work. ADR-074 made the same change for the spec stage (12 to 20).
Decision: `stages.build.turns` in `.github/sdlc-config.json` goes from 40 to 60, and the built-in `"build"` turns in `src/sdlc_engine/__init__.py` go to 60 too, so `tests/test_sdlc_config_file.py` (which keeps the file equal to the built-in values) still passes. No other stage changes: intent stays at 12, spec 20, plan 15, review 15, release 10, the support stages 10, 15 and 20. `docs/SDLC.md` names the new range (10 to 60).
Consequences: a build run can cost more tokens, up to 60 turns before it is stopped. The cap stays soft, since the action checks it after the run ends, so some margin is still needed and a run near 60 can still lose its work. Keeping the finished work of a run that ended in success is a separate, larger change and is not made here. If a build slice still overruns at 60, shrink the slice in the issue comment; do not raise the limit again without a decision. `.github/` and `src/sdlc_engine/` are protected paths, so this change needs a human merge. Not verified: no real build run has happened since the change.

## ADR-077 · 2026-11-25 · The plan stage's turn budget is 25 (#118)
Context: the plan stage still has its original cap of 15. ADR-074 raised the spec stage from 12 to 20 and ADR-076 raised the build stage from 40 to 60, because the action enforces a stage's cap after the run ends, so a run that overshoots loses its finished output. The plan stage writes `plan.md`, which the build stage needs as its input, so a plan run that is cut off at the cap leaves the next stage with nothing to read.
Decision: `stages.plan.turns` in `.github/sdlc-config.json` goes from 15 to 25, and the built-in `"plan"` turns in `src/sdlc_engine/__init__.py` go to 25 too, so `tests/test_sdlc_config_file.py` (which keeps the file equal to the built-in values) still passes. No other stage changes: intent stays at 12, spec 20, build 60, review 15, release 10, the support stages 10, 15 and 20. `docs/SDLC.md` names no plan cap (it gives the range 10 to 60, which still holds), so it is unchanged.
Consequences: a plan run can cost more tokens, up to 25 turns before it is stopped. The cap stays soft, since the action checks it after the run ends, so a run near 25 can still lose its output. If a plan still overruns at 25, shrink the slice in the issue comment; do not raise the limit again without a decision. `.github/` and `src/sdlc_engine/` are protected paths, so this change needs a human merge. Not verified: no real plan run has happened since the change.

## ADR-078 · 2026-11-26 · Phase C is closed: LEGACY fallbacks removed, authorization.yaml read from the profile only (#118, #123, #125)
Context: ADR-075 moved all owner-specific data under profiles/<id>/ and kept the LEGACY fallbacks (c) and the root authorization.yaml (d) for last. The code for (c) landed in #128 (issue #123): the LEGACY fallbacks are removed, a stale root copy of reports/, state/, applications/ or a non-empty logs/runs.jsonl is refused, and the decide install template is fixed. The code for (d) landed in #129 (issue #125): the code reads authorization.yaml only from profiles/<id>/ and fails closed. #124 and #126 added the intent, spec, plan and the decide fixture only; they changed no code.
Decision: (a) no root fallback exists for reports, state, applications, runs, the apply section of the config or the failure lines. A data repo without a profile folder is a ConfigError, and so is several profiles without an explicit choice. A failure line with no profile folder cannot be written (ConfigError); reading the failure lines with no profile folder returns nothing, so the failure email still sends. (b) apply_path loses its root branch: no profile folder is a ConfigError. (c) apply_cfg raises ConfigError for an unknown profile id, and for no profile id when there are zero or several profiles. (d) the installed decide.yml is checked on every test run against the committed fixture tests/fixtures/decide.installed.yml. The comparison ignores blank lines, comment lines and lines that name a path; those path lines are then compared on their own. The fixture is refreshed whenever the installed file changes. (e) a missing profiles/<id>/authorization.yaml is a ConfigError, so validate exits 2 and the pipeline stops before it collects anything. A root authorization.yaml is never read, with or without a profile copy; the stale-root guard does not cover it. (f) no code rollback after merge.
Consequences: the scan routine was paused for the authorization move in career-data and resumed only after the checks passed on main. The fixture can drift from the installed file until it is refreshed by hand. .github/** in career-data is human-edited, so installing a new decide.yml is an owner step.
Not verified: the first scheduled run after the move (see the scan-review of that run).

## ADR-079 · 2026-11-26 · Every profile-scoped apply subcommand takes --profile; enqueue refuses a profile mismatch
Context: ADR-069 (c) says the profile id "must be given with --profile when there are several". After ADR-078 only `run` and `bundle` accepted it. `summary` read a profile attribute its parser never added, and `main()` resolved a profile for every command, so `blacklist` and `bundle` failed with several profiles too. No issue was opened for this change; the scope is the apply-subcommand list below.
Decision: (a) `enqueue`, `approve`, `skip`, `done`, `track`, `followed-up`, `questions` (every action) and `summary` take `--profile` and act only on that profile's queue, answers and reports. (b) `main()` resolves a profile only for commands that act on one; `blacklist` and `bundle` need none. Authorization is read only by `run`, for its profile, and by `enqueue`, per row. (c) `enqueue`: a row's own `profile` is authoritative. An explicit `--profile` that disagrees with a row refuses the whole candidates file: exit 2, nothing written. A row without a profile takes `--profile`, or the only profile. Several profiles with neither is refused. (d) Each row is judged with its own profile's apply policy and authorization (`load_authorization` for that id, fails closed, ADR-042). Queues are saved only after every row has been checked.
Consequences: code only (ADR-063); no data change and no root fallback (ADR-078). An item queued with no profile of its own now records the resolved profile id. Single-profile behaviour is unchanged for every subcommand. Untested on real data: a two-profile dry run by the owner.

## ADR-080 · 2026-11-26 · Remotive queries, SourceHealth, and Working Nomads as a public_api source with its terms pending
Context: the owner supplied three job-board searches for the scheduled scan and email. Remotive is already a source; its website filters (location, skills, language, min_salary) are not API filters. Working Nomads publishes one public JSON feed (`/api/exposed_jobs/`, a JSON array). Jobgether publishes a public search API (ADR-081). The website search pages are not scraped (ADR-008). The sandbox could not reach workingnomads.com or jobgether.com (the egress proxy refused them and the web-fetch stand-in could not resolve them), so neither site's terms were read on 2026-11-26.
Decision: (a) Remotive: per-skill search queries are added to the owner's search plan (`profile.yaml → daily_queries`); the website's location, skills, language and min_salary filters are not API filters and are replaced by scoring and `location_rules`. (b) SourceHealth: collect records each configured source as `ok`, `empty-unexpectedly` (every query ran and returned zero candidates), `failed` (a query raised) or `not-run` (blocked or over budget). The status is written to `candidates.json`, printed in the RUN SUMMARY, and shown in the report and the email, so a silent empty source is visible (ARCHITECTURE §2b). `empty-unexpectedly` does not by itself change whether an email is sent. (c) Working Nomads: the adapter fetches the feed once per process and filters locally by a case-insensitive substring over title, tags and description. Its manifest leaves `terms_reviewed` unset, and collect does not run a declared source whose terms are not reviewed. **Pending, not shipped as enabled:** the adapter is built and tested against a hand-trimmed fixture; it runs only after the owner records the terms review and a recorded response is checked against the fixture. (d) Jobgether: **pending, not shipped.** No adapter exists. It waits for the owner's sample response and terms; the repost rule is in ADR-081.
Consequences: Jobgether URLs, when that adapter exists, are listing pages, not apply links. The routine's network allowlist must include remotive.com (already in use) and workingnomads.com before that source is enabled; the owner adds the hosts. Remotive's API terms ask that listings be linked back and named, and not be put on third-party sites; the owner's email is the only destination. Manifests exist for remotive and workingnomads only: arbeitnow, adzuna and jsearch have none yet, so the terms gate does not cover them. If a terms review forbids a source, that source is dropped by amending this ADR.

## ADR-081 · 2026-11-26 · Jobgether reposts: one candidate per company and normalised title across a run (decision only; no adapter yet)
Context: Jobgether reposts one role per country under new IDs (the owner's observation of the Jobgether API, to be verified on the owner's sample). ADR-063 was cited for this in error: it records the Glassdoor run lessons and says nothing about reposts. The normalisation helpers already exist in `normalize.py` (`norm_text`, `candidate_key`), but `candidate_key` keys on the source ID first, so reposts under new IDs would not collapse.
Decision: when the Jobgether adapter is built, candidates from all queries in one run are grouped by (normalised company, normalised title) with `norm_text`. One candidate is kept per group. The kept posting is the one whose location is Portugal or anywhere (in that order); otherwise the first seen. The collapse runs in the adapter's per-run scope, so the same role from two countries appears once. It is tested with a recorded pair of reposts before the adapter ships.
Consequences: no code is written by this ADR. The Jobgether adapter is pending the owner's sample response and terms (ADR-080 d). If the collapse proves wrong on the sample, this ADR is amended, not silently changed.

## ADR-082 · 2026-11-27 · The SDLC engine moves to a shared public repo, sdlc-engine (S3)
Context: the agentic SDLC (engine, reusable stage workflow, goldens; ADR-064 to ADR-068, ADR-073 to ADR-077) lives inside career-ai. A second project, motion-blueprint-app (a public JavaScript PWA with npm tests), will use the same workflow. career-data stays out: it holds personal data and the agents can read a whole repo they run in (non-negotiables 1 and 2).
Decision: (a) a public repo RASMiranda/sdlc-engine holds the stdlib-only engine, the reusable workflow sdlc-stage.yml, template/ for new projects and the docs. (b) Each project keeps a thin caller sdlc.yml, .github/sdlc-config.json (with config_version), its agents, labels, REVIEW.md and CODEOWNERS. (c) A project pins the engine by the full 40-hex commit SHA of a release, with a "# vX.Y.Z" comment; never @main, never a tag. (d) Releases follow SemVer 0.y.z until 1.0 (a breaking change bumps the minor and says BREAKING in CHANGELOG.md); tags vX.Y.Z are annotated and protected by a tag ruleset. (e) Licence: MIT, matching motion-blueprint-app. (f) One CLAUDE_CODE_OAUTH_TOKEN per project repo; the Pro quota is shared and each budget gate counts only its own repo. (g) A bump is a PR in the project (Dependabot or by hand), a protected-path PR merged by a human, followed by a canary intent run; rollback is a revert. (h) The engine repo is locked down harder than the projects: rulesets on main and on tags, read-only Actions permissions, no secrets, immutable releases if the plan offers them. (i) A check-project command compares the pin, the config_version and the engine input.
Consequences: an engine fix reaches a project only through a bump PR, so a fix is two merges per project. Every project can lag; check-project reports it. A compromised engine repo reaches every consumer's token, which is why (c) and (h) exist. This ADR changes no code and no workflow; the extraction itself is built in later steps. Not verified: whether Dependabot bumps a SHA-pinned reusable-workflow reference; how a called workflow learns its own commit (a spike measures it before the cross-repo step); whether immutable releases are available on this plan.
