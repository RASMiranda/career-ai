# Roadmap — phases with exit criteria and the Claude Code prompt for each

Work in order. Do not start a phase until the previous exit criterion is met.
Each prompt is run in Claude Code, inside `career-ai`.

## P0 · Prove it for one person (now)
Do: setup per GETTING-STARTED.md; manual apply mode; fill the five knowledge docs.
Sources for P0: only the four already implemented (Remotive, Arbeitnow, Adzuna,
JSearch). The registry in `career-data/config.yaml` lists the rest as planned.
Measure per run: candidates, emailed, opened by you, dismissed as noise, minutes
spent. The criteria file should include 5-10 past postings labelled would-open /
would-not, as the baseline for false positives.
Exit: two weeks of dry runs where you would genuinely open most emailed matches.

## P1 · Two more users, separate data
Do: one **private data repo per person** (never share one repo between people);
same engine, different `--data`.
Exit: both use the digest weekly without your help. If they do not, stop here.

## P2 · Tenant-ready engine
```
Read CLAUDE.md and src/jobscan. Refactor for multi-tenancy without changing
behaviour; all tests must still pass.
1. Add TenantContext (user_id, profile_id, entitlements) passed to every step.
2. Define Protocols: Source, Evaluator, Notifier, Store, ApplyAdapter. Move file
   and state code behind FileStore. Sources become registered plugins, each with
   a JSON-schema for its params.
3. Load config from the Store, not hard-coded paths.
3b. Add SourceManifest (id, access_method enum with no "scrape", terms_reviewed,
   rate_limit, redistribution_allowed, params JSON-schema). The registry rejects a
   manifest with missing fields or a denylisted domain (LinkedIn first). Add
   SourceHealth (ok | degraded | empty-unexpectedly | failed) per source per run
   and have the Notifier report any change. Implement ats_board (greenhouse,
   lever, ashby) and hn_hiring as the first new plugins, tested against recorded
   fixtures with no live network in tests.
4. Add a UsageLedger recording API calls and LLM tokens per tenant per run.
5. Add tests for every seam using fakes, plus: incomplete manifest rejected,
   denylisted domain rejected, every plugin's output validates as a Candidate,
   an unexpectedly empty source raises SourceHealth, not silence.
Do not add a web server, database or auth yet.
```
Exit: a second tenant runs from a fake in-memory Store in tests.

## P3 · Postgres store + isolation
```
Add PostgresStore and SQL migrations for the tables in docs/ARCHITECTURE.md §3,
with row-level security. Run Supabase locally. Add a test proving user A cannot
read or write user B's rows through any table. Keep FileStore working.
```
Exit: isolation test green; both stores pass the same contract tests.

## P4 · API evaluator with cost control
```
Add ApiEvaluator using the Claude API: small model for triage, escalate only
fit 60-85 to a larger model, cache the criteria prompt, enforce a hard token cap
per run in code, write every call to UsageLedger. Add a deterministic pre-filter
(dedupe, blacklist, seniority/title rules) before any LLM call. Report cost per
run.
```
Exit: measured cost per user-month on real data.

## P5 · Portal MVP
Before coding, mock the five screens as one clickable HTML artifact in the
Claude Project. Then:
```
Create an Angular app with supabase-js: Google/GitHub OAuth; screens for profile
& criteria (markdown), sources (form generated from each plugin's JSON-schema),
blacklist, notifications, applications queue. No billing yet. RLS enforces
isolation; add an e2e test for it.
```
Exit: a friend completes onboarding unaided and receives a digest.

## P6 · Billing
```
Add Stripe Checkout and a webhook handler that writes subscriptions and
entitlements. The worker reads only entitlements. Test: webhook replay is
idempotent; cancelling downgrades limits at period end.
```

## P7 · Assisted apply for users (browser extension / local agent)
Fill-and-pause on the user's own machine with a per-application consent record.
No server-side submission. Legal read of ATS terms first.

## P8 · Launch checks
Privacy policy, DPA, export/delete, retention, sub-processor list, breach
procedure, abuse/rate limits, cost alerts. Lawyer review.
