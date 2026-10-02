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

## Template
## ADR-n · YYYY-MM-DD · Title
Context: … · Decision: … · Consequences: …
