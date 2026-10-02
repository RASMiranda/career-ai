# Career AI — architecture

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
| `Source` | functions in `sources/`, params in `config.yaml` | plugin registry; each declares a JSON-schema for its params; the portal renders the settings form from the schema, so a new source needs no UI work |
| `Evaluator` | Claude inside the routine | API worker: small model for triage, larger for borderline; cached criteria prompt; hard token cap per run |
| `Notifier` | Gmail connector | email, Telegram, Slack per user |
| `Store` | files in the private repo | Postgres, `user_id` on every row, row-level security |
| `ApplyAdapter` | `FormAdapter` (ATS pages) | + email-apply; adapters run on the user's machine/extension |
| `Blacklist` | `config.yaml` | per-user table + optional global defaults |
| `Entitlements` | n/a | table read by the worker; plans are data, not code |

Rules that keep it clean: the engine takes a `TenantContext` (user, profile,
entitlements); no step reads globals or hard-coded paths; the worker never
knows about Stripe, only about entitlements.

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
- The model has no network tools, no browser, no send capability.
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
