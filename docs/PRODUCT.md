# Career AI — product definition (v0, hypotheses marked)

## Who it is for
Senior professionals, freelancers and contractors who want **fewer, better**
opportunities: people with a clear direction who are drowning in alert noise.
First users: the owner, then two family members (separate profiles, separate
data).

## Core promise
"Tell it once what you want and what you refuse. It finds, scores and explains
matches, and hands you ready-to-act applications. You stay in control."

## What it does
1. Collects jobs from configurable sources (APIs, feeds, email alerts).
2. Removes duplicates and blacklisted companies deterministically.
3. Scores fit against **your** written criteria, with a reason and a caution.
4. Delivers a short digest.
5. Queues applications; you apply manually, or (opt-in) it fills the form and
   you click submit, or (opt-in, strictly bounded) it submits within caps.
6. Logs every failure in a redacted form so the tool improves.

## What it is not
- Not a mass-apply bot. Quality and fit over volume.
- Not a LinkedIn scraper or Easy-Apply automator.
- Not a CAPTCHA solver, not an identity-spoofing tool.
- Not a promise of interviews or offers.

## Free vs paid (HYPOTHESIS — validate with real users before building billing)
| | Free | Paid |
|---|---|---|
| Profiles | 1 | several |
| Sources | public boards only | + keyed APIs, email-alert ingestion |
| Scans | weekly | daily |
| Scoring | capped LLM calls / month | higher cap, better model |
| Applications | manual queue | assisted fill (browser extension / local agent) |
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
white-label, any server-side auto-submission on behalf of paying users.
