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

