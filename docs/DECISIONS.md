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
by `authorization.yaml`. The ADR-003 claim is amended to "mitigated in P0,
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
