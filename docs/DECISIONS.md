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

## ADR-004 · 2026-10-02 · Application submission is opt-in and bounded
Decision: default `manual`; `assisted` and `auto` behind a master switch with a
dated acknowledgement, caps, allow-listed adapters, and a redacted failure log.
Never: CAPTCHA solving, LinkedIn automation, auto-answering legal questions.
Consequences: expect many "hand to human" outcomes; that is correct behaviour.
*Amended by ADR-017 (2026-10-08): "LinkedIn automation" is no longer a blanket ban; the
CAPTCHA and legal-question rules stand.*

## ADR-005 · 2026-10-02 · Blacklist enforced three times
Decision: filter in `collect`, fail in `validate`, refuse in `apply`.
Defaults seeded: Micro1, Crossing Hurdles, Proxify, Alignerr.
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

