# Reference product: aiapply.co

Since 2026-10-08 (ADR-017) the product aims to stay **as close as possible to
[aiapply.co](https://aiapply.co)** in what it offers and how a person uses it.
This page is the working comparison. Check it before designing a feature, and
update it whenever either side changes.

## How reliable this page is

The development sandbox cannot reach aiapply.co (the network policy blocks it), so
everything below about AIApply comes from **third-party reviews, directory listings
and AIApply's own replies on Trustpilot**, found on 2026-10-08. Treat the right-hand
column as the checked one and the left as a claim to confirm. Open the real site once
and correct any row marked `?`; prices and modes in particular change.

Sources: [Scoutify review](https://scoutify.com/blog/aiapply-review) ·
[Techjockey listing](https://www.techjockey.com/detail/aiapply) ·
[Jobright review](https://jobright.ai/blog/aiapply-review-2026-how-it-works-pricing-and-honest-user-experiences/) ·
[Trustpilot](https://nl-be.trustpilot.com/review/aiapply.co) ·
[Jobscan comparison](https://www.jobscan.co/blog/jobscan-vs-aiapply/) (a competitor: weigh it accordingly).

## Parity matrix

Status: **have** = works today · **added** = built with ADR-017 · **partial** ·
**gap** = not built · **differs** = deliberately not the same (reason below).

| AIApply offers (as reported) | Here | Status |
|---|---|---|
| Onboarding: upload a CV or import LinkedIn, set job preferences (level, minimum salary, industry, role, location, work format) | `profiles/<id>/profile.yaml`, `01-knowledge/05-job-match.md`, CV cards; `add-profile` skill; LinkedIn export kept in `02-sources/`. File-based; a form is P5 | have |
| Job board (about 600k jobs, 20+ countries) and listings from LinkedIn, Indeed, Glassdoor and company pages | Remotive, Arbeitnow, Adzuna, JSearch (an API that itself aggregates the large boards), ATS boards planned. No in-app board: the digest email is the feed | partial |
| Direct reading of LinkedIn / Indeed / Glassdoor | Permitted on the owner's machine by ADR-017, **no code yet** (see "Not built blind") | gap |
| Match selection from the preferences | Scored against written criteria with deal-breakers; deterministic prefilter first (titles, stack terms, **languages**) | have, stricter |
| Auto-apply, submitting without a pause ("Auto") | `apply.mode: auto` behind `authorization.yaml` (switch + dated acknowledgement), caps, adapters for Greenhouse, Lever, Ashby | have |
| "Human-in-the-Loop": each application held until approved | `apply approve`, and `assisted` mode (form filled, you click submit) | have |
| Auto-apply on LinkedIn Easy Apply, Indeed, Glassdoor, career pages | Needs adapters per site and the owner removing `apply_via_linkedin_easy_apply` from `forbidden_actions` | gap |
| One credit per auto-application, bundles of credits | Per-day and per-week caps in `config.yaml → apply.auto`; usage ledger and billing are P4 / P6 | partial |
| Application Kit: resume and cover letter tailored to a job description | `python -m jobscan.kit`: per job a tailored summary, what to emphasise in the chosen CV, honest gaps, and a cover letter; the CV variant is already chosen per job | **added** |
| Follow-up email | Drafted by the kit; the tracker says when one is due; you send it | **added** |
| Application tracker (applications and responses) | `apply track`, funnel and "follow up" / "in progress" in the daily summary | **added** |
| Interview Buddy: practice questions with answers | The kit's `interview-prep.md`: likely questions with outlines grounded in your CV, and questions to ask | **added** (preparation only) |
| Real-time answers during a live interview | Not planned (see below) | differs |
| Mock interviews with feedback | Not built. `interview-prep.md` can be used as the script in a normal Claude chat | gap |
| Resume builder from scratch, ATS-optimised, several versions per role type | CV variants and cards (`cv/`) plus the `cv-tailoring` skill for the Word file. No generator from a blank page | partial |
| Resume translation into EU languages | The kit writes the letter, follow-up and summary in any language the profile speaks at working level (`languages`); translating the CV file itself is still by hand | partial |
| Resume scanner / ATS score `?` | Not built. The kit's `gaps` is the nearest thing | gap |
| Shareable resume link with view tracking | Needs a web service (P5) | gap |
| Accounts, billing, plans | One owner today; entitlements and Stripe are P5 / P6 | gap |

## Where it deliberately differs

1. **Fewer, better.** AIApply's most repeated public complaint is relevance: matches
   that ignore location, seniority or language, with its own support admitting the
   exclusion filters did not always work. This engine exists to avoid that, so
   parity means the same workflow and features, **not** the same volume or the same
   weak targeting. Scoring, deal-breakers, the blacklist and the language prefilter
   stay in front of every apply step.
2. **The model never drives the browser** (ADR-003, ADR-007). A posting is untrusted
   text; an LLM that clicks and submits can be told to by the posting. Submission is
   deterministic code on the owner's machine. This costs no feature AIApply offers.
3. **No server-side submission for paying users** until a lawyer has read the ATS
   terms (ARCHITECTURE §6). Nobody pays yet.
4. **No CAPTCHA solving, no evasion** of a site's bot detection, and no answering
   legal or work-authorisation questions unless the owner wrote the answer.
5. **No live interview copilot.** It needs a live audio client, and answering for the
   candidate in real time is a different product from preparing them.
6. **Review before sending is the default**, not an option you find after the first
   bad batch. `manual` is still the shipped mode.

## Not built blind

LinkedIn, Indeed and Glassdoor adapters (reading listings, Easy Apply) are allowed by
ADR-017 but were not written in the session that wrote it. They cannot be reached from
the development sandbox, so any selector would be a guess, and a wrong guess on a
logged-in account is how accounts get restricted. Build them on the owner's machine,
headed, against recorded pages as test fixtures, one source at a time, following the
conditions in ADR-017. Until then JSearch already returns listings from the same boards
through a licensed API, which covers discovery.

## Keeping this page honest

- When a feature ships, move its row to **added** and link the code or doc.
- When you read aiapply.co directly, replace the third-party claims and delete the `?`.
- When the two products diverge for a reason, add it to "Where it deliberately differs"
  instead of leaving a silent gap.
