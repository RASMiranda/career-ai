# Career AI — product definition (v0, hypotheses marked)

## Who it is for
Senior professionals, freelancers and contractors who want **fewer, better**
opportunities: people with a clear direction who are drowning in alert noise.
First users: the owner, then two family members (separate profiles, separate
data).

## Reference product
The product aims to stay **as close as possible to [aiapply.co](https://aiapply.co)**
(ADR-017): the same journey of preferences in, matches found, documents tailored,
applications sent or prepared, responses tracked, interviews practised. The
feature-by-feature comparison, what is built and what differs on purpose are in
`REFERENCE-AIAPPLY.md`. Where we differ it is on match quality and safety, never on
what the person can do.

## Core promise
"Tell it once what you want and what you refuse. It finds, scores and explains
matches, and hands you ready-to-act applications. You stay in control."

## What it does
1. Collects jobs from configurable sources: open and keyed APIs, feeds, company
   ATS boards, and alert emails (see ARCHITECTURE §2b).
2. Removes duplicates and blacklisted companies deterministically.
3. Scores fit against **your** written criteria, with a reason and a caution.
4. Delivers a short digest.
5. Queues applications; you apply manually, or (opt-in) it fills the form and
   you click submit, or (opt-in, strictly bounded) it submits within caps. An application that
   fails, or that the runner never submits, is the first thing in the next email, so you can apply by hand.
6. Drafts the **Application Kit** for a match on request: cover letter, a tailored
   summary and what to emphasise in the chosen CV (with the gaps it must not claim),
   a follow-up email and interview prep, in a language the person speaks.
7. Tracks what came back (reply, interview, offer, rejection), shows the funnel, and
   says which applications have gone quiet and are due a follow-up.
8. Logs every failure in a redacted form so the tool improves.

## What it is not
- Not volume for its own sake. Volume is a setting (`apply.auto` caps); the default
  stays conservative and the scan's match quality sits in front of every apply step.
- Not an LLM that drives a browser or submits (ADR-003): the model scores and drafts,
  code acts.
- Not a CAPTCHA solver, and not a tool that spoofs identity or evades bot detection.
  Direct access to closed platforms, where built, stops at the first block signal
  (ADR-017).
- Not a live interview copilot.
- Not a promise of interviews or offers.

## Sources
Sources are configuration. Each is enabled per profile and declares how it is
reached. Registered today: Remotive, Arbeitnow, Adzuna, JSearch (in use);
Greenhouse, Lever, Ashby, Hacker News "Who is hiring" (planned, P2); LinkedIn,
Indeed, Glassdoor, Braintrust (registered; alert emails or manual channel);
Malt, Toptal, Shakers, Turing (manual checklist). Direct access to the closed
platforms is allowed in principle on the owner's own machine under the conditions
in ADR-017, and is not built yet; JSearch already carries listings from the same boards.

## Free vs paid (HYPOTHESIS — validate with real users before building billing)
| | Free | Paid |
|---|---|---|
| Profiles | 1 | several |
| Sources | public boards only | + keyed APIs, email-alert ingestion |
| Scans | weekly | daily |
| Scoring | capped LLM calls / month | higher cap, better model |
| Applications | manual queue, kit, tracker | assisted fill (browser extension / local agent); the "credits" AIApply sells map to these caps |
| Notifications | email | + Telegram / Slack |
| History | 30 days | full |
Pricing is deliberately not set here: derive it from measured cost per user.

## Success measures (in order of importance)
1. Opportunities the user actually explored, per month.
2. Interviews per explored opportunity.
3. False-positive rate (noise the user had to dismiss).
4. Weekly human minutes spent.
5. Cost per active user per month.
Not a goal: number of applications sent.

## Out of scope until the core is proven
Mobile app, CV generation marketplace, recruiter CRM, team accounts,
white-label, any server-side auto-submission on behalf of paying users (until a
lawyer has read the ATS terms), a real-time interview copilot.
Direct access to closed platforms (LinkedIn, Indeed, Glassdoor, Braintrust) for anyone
but the owner, on the owner's machine (ADR-017).
