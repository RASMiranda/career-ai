# Career AI — architecture

Reference product: [aiapply.co](https://aiapply.co) (ADR-017, `REFERENCE-AIAPPLY.md`).

Goal: run free for one person today; become a multi-tenant, OAuth-protected,
configurable, subscription product without a rewrite. Everything user-specific
is **data**, everything behaviour-specific sits behind an **interface**.

## 1. Today (single user, free)

```
 Claude Code routine (cloud, weekdays)          your machine (optional)
 ┌───────────────────────────────────┐          ┌──────────────────────────┐
 │ collect → [Claude scores] → validate│          │ apply run (Playwright)   │
 │ → enqueue → summary → report → mail │          │ assisted | auto          │
 └───────┬──────────────────┬─────────┘          └───────────┬──────────────┘
         │ clones            │ pushes state                   │ pulls/pushes queue
   career-ai (public)   career-data (PRIVATE) ◄───────────────┘
   code, tests, prompts  criteria, state, queue, logs, reports
```

## 2. Seams that make it scalable

| Seam | Today | Product |
|---|---|---|
| `Source` | `REGISTRY` in `sources/` (name → fetch function); queries and params in `config.yaml` | plugin registry; each plugin ships a manifest (access method, terms status, rate limit, params JSON-schema); the portal renders the settings form from the schema, so a new source needs no UI work |
| `Evaluator` | Claude inside the routine | API worker: small model for triage, larger for borderline; cached criteria prompt; hard token cap per run |
| `Notifier` | Gmail connector | email, Telegram, Slack per user |
| `Store` | files in the private repo | Postgres, `user_id` on every row, row-level security |
| `ApplyAdapter` | `FormAdapter` (ATS pages) | + email-apply; adapters run on the user's machine/extension |
| `Blacklist` | `config.yaml` | per-user table + optional global defaults |
| `Entitlements` | n/a | table read by the worker; plans are data, not code |

Rules that keep it clean: the engine takes a `TenantContext` (user, profile,
entitlements); no step reads globals or hard-coded paths; the worker never
knows about Stripe, only about entitlements.

## 2b. Source registry (sources are configuration, not code paths)

Every job source is a registry entry. Enabling, disabling or adding one is a
config change; a new *kind* of source is a plugin.

**Access methods** (the only allowed values; there is deliberately no `scrape`; `owner_browser` is
the only way to reach a closed platform directly, see below and ADR-017):

| `access_method` | Meaning | Examples |
|---|---|---|
| `public_api` | Open JSON API, no key | Remotive, Arbeitnow, Hacker News "Who is hiring" (Algolia) |
| `keyed_api` | Official API with a key and quota | Adzuna, JSearch (RapidAPI) |
| `feed` | RSS/Atom | We Work Remotely and similar |
| `ats_board` | Per-company public job board of an applicant-tracking system; you configure *which companies*, it does not search the market | Greenhouse, Lever, Ashby (Workable, SmartRecruiters, Recruitee: same shape, to verify) |
| `email_alert` | Alert emails the user receives or forwards | LinkedIn, Indeed, Glassdoor, Braintrust (if it sends alerts) |
| `manual_channel` | No machine access; listed as a checklist in the report | Malt, Toptal, Shakers, Turing |
| `clip` | A page the owner saved from any site; the `JobPosting` JSON-LD in it is read from disk (`jobscan.clip`). No network, login or selectors; `collect` ingests `inbox/clips.json` like a source | LinkedIn, Indeed, Glassdoor, company career pages |
| `owner_browser` | *Not implemented.* The owner's own logged-in browser on the owner's machine, visible, slow, opt-in per source, stops at the first block signal. Never in the cloud routine | LinkedIn, Indeed, Glassdoor (when built) |

**Manifest** every plugin declares: `id`, `access_method`, `terms_reviewed`
(date + link), `rate_limit`, `redistribution_allowed` (matters for the paid
product: aggregator terms often restrict storing or reselling results), `params`
(JSON-schema). The registry refuses a plugin missing any field. All sources emit
the one normalised `Candidate`; blacklist and dedupe run after normalisation.

**Closed platforms** (LinkedIn, Indeed, Glassdoor, Braintrust) are registered
now so the source list is complete, with `email_alert` or `manual_channel` as the
provisional method. ADR-017 supersedes the "not approved" of ADR-008: direct access
is allowed as `owner_browser` under these conditions, all of them: opt-in per source
with `terms_reviewed`; owner's machine only; visible by default; capped by
`rate_limit`; first block signal (CAPTCHA, login wall, "unusual activity", 403/429)
ends the source for that day as `SourceHealth: failed`; no spoofing, proxy rotation or
CAPTCHA solving; adapters tested against recorded pages. None is written yet.

**SourceHealth** (per source, per run): `ok | degraded | empty-unexpectedly |
failed`. The Notifier alerts on any change. A source that silently returns zero
results is worse than one that errors, because it quietly breaks "fewer, better".
Today `collect` records per-source errors in `candidates.json`; the status model
is P2 work.

**Status as of 2026-10-02**

| Source | Method | State |
|---|---|---|
| remotive, arbeitnow, adzuna, jsearch | public_api / keyed_api | implemented, in use |
| greenhouse, lever, ashby | ats_board | planned (P2); public endpoints answered HTTP 200 on 2026-10-02, terms not reviewed |
| hn_hiring | public_api | planned (P2); endpoint answered HTTP 200 on 2026-10-02, terms not reviewed |
| linkedin, indeed, glassdoor | email_alert | registered, not implemented; alert ingestion waits on the routine-exposure review (ADR-007) |
| braintrust | email_alert / manual_channel | registered; verify whether any API or alert email exists |
| malt, toptal, shakers, turing | manual_channel | listed in `config.yaml → manual_channels` |

## 2c. After a match: kit and tracker

```
queue (applications/queue.json)           profiles/<id>/03-outputs/<date>-<company>-<title>-<key>/
  queued → approved → submitted | done       cover-letter.md  cv-tailoring.md
                          └→ replied → interview → offer       follow-up-email.md  interview-prep.md
                          └→ rejected | withdrawn
```

- `jobscan.kit prepare` → model drafts → `jobscan.kit finish` (ADR-003 again: the model
  writes, code validates and files). `finish` fails closed and writes nothing if any
  draft has a link, address, phone number, HTML, an unfilled placeholder, a language
  the profile does not speak, a size out of range, or a letter that never names the
  company. It never reads `applicant` or `answers`. The posting text stored in the queue
  (`description`, 2500 characters) is the only input besides the CV cards and knowledge
  files, and it is passed as untrusted data.
- `apply track` / `followed-up` move an applied item along; `summary` shows the funnel,
  what is in progress, and what is due a follow-up (`apply.follow_up_days`, default 7;
  a profile may override with `follow_up_days`). Nothing here contacts anyone.
- The scan routine does not run the kit (usage is limited); the owner does, on request,
  and commits `profiles/` and `applications/` in `career-data` afterwards.

**Form answers (ADR-019).** The adapter's `UNKNOWN_REQUIRED_FIELD` failure now carries each
unanswered question's `kind`, `options` and `max_length`. `apply questions prepare` turns recent
failures into a brief, a model drafts, `finish` validates and stores `proposed` answers in
`applications/answers.json`, and **the owner approves each one** (`approve`, `reject`, `set`). Only
`approved` ones reach a form, through `answers_for`, after the owner's explicit `profile.yaml →
answers`. Questions in `OWNER_ONLY` (legal, consent, demographic, pay, notice, start date, any
checkbox, date, email or phone field) never reach the model: they are stored as `needs_owner`.
The model sees the question, the job and the CV cards, never `applicant` or `answers`.

## 3. Data model (multi-tenant)

`users` · `profiles` (criteria markdown, per user) · `source_configs`
(type, params json, enabled) · `blacklist_entries` (user, name, aliases,
domains, scope) · `integrations` (encrypted tokens) · `runs` · `candidates` ·
`decisions` · `seen` · `application_queue` · `application_attempts` (code,
step, redacted details) · `consents` (what the user authorised, when, for what
cap) · `usage_ledger` (API calls + LLM tokens per run) · `subscriptions` ·
`entitlements`.
Row-level security on all of them, with a test proving user A cannot read
user B.

## 4. Product stack (suggested, you are a Java/Angular engineer)
- **Worker**: keep the Python engine (tests exist).
- **DB + auth**: Supabase (Postgres, Google/GitHub OAuth, RLS). *Check current
  free-tier limits and pausing rules before relying on them.*
- **Portal**: Angular + supabase-js. Screens: sign in · profile & criteria ·
  sources · blacklist · notifications · applications queue · billing.
- **Billing**: Stripe Checkout + webhooks → `subscriptions` → `entitlements`.
- **Scheduler/worker hosting**: start with a scheduled job (GitHub Actions cron
  or similar); add a real queue only when volume forces it.
- **LinkedIn alerts**: give each user an inbound address (Postmark inbound or
  Cloudflare Email Routing) and have them forward alerts. This avoids Gmail
  OAuth, which uses a restricted scope that, as far as I know, needs Google
  app verification and an annual security assessment — verify before choosing.

## 5. Security model
- Secrets: never in repos, never in the model context. Today: cloud-environment
  API credentials. Product: a secrets manager; integration tokens encrypted at
  rest, decrypted only inside the worker.
- Untrusted input: job text, alert emails, web pages. The model returns a
  schema-validated decision and nothing else; the validator fails closed.
- Target (P4 `ApiEvaluator`): the model has no network tools, no browser, no send
  capability. In P0 the routine session has a shell and the Gmail connector, so
  the guarantee is *mitigated, not eliminated*: custom network allow-list,
  proxy-injected API credentials, Gmail as the only connector (ADR-007).
- Every external effect passes through code that checks `authorization`
  (today a YAML file, later `entitlements` + `consents`).
- Logs are redacted at write time; bundles shared with an AI contain no names,
  emails, phones, companies, titles or URL paths.

## 6. Application submission — design decisions
- Default **manual**. `assisted` fills the form in a visible browser; the human
  clicks submit. `auto` is bounded by master switch, dated acknowledgement,
  min fit/confidence, per-day and per-week caps, one application per company per
  window, adapter allow-list, blacklist.
- Deterministic adapters, not an LLM-driven browser: a posting can contain
  instructions aimed at an agent.
- Unknown required question, consent box, work-authorisation question, CAPTCHA,
  login wall, changed layout → stop, log, hand to the human with the link.
- **Unchanged by ADR-017:** the model never drives the browser, and the
  product implication below stands until legal advice says otherwise.
- **Product implication:** do not run server-side auto-submission for paying
  users. It combines ATS terms-of-service exposure, bot detection that harms the
  user's reputation, and liability for wrong answers. Ship `assisted` through a
  browser extension or local agent running on the user's own machine, with a
  per-application consent record. Revisit `auto` only with legal advice.
  Check each ATS's terms on automated submission; I have not verified them.

## 7. Cost model (do this before pricing)
Per active user per month ≈ source API calls + LLM tokens (candidates scored ×
tokens each) + email + hosting. Controls, in order of impact: deterministic
pre-filter before any LLM call (dedupe, blacklist, title/seniority rules) →
small model for triage, escalate only borderline → cached criteria prompt →
per-run token cap enforced in code → `usage_ledger` per tenant. Measure with
your own account for two weeks, then set prices.

## 8. Compliance checklist (before charging anyone)
CVs are personal data under GDPR and the operator is a Portuguese company:
privacy policy, DPA, data-subject export and delete, encryption at rest,
retention limits, sub-processor list (LLM provider, database, email), lawful
basis, breach procedure. Have a lawyer read them; this document is not legal
advice.
