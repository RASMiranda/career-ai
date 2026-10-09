# Reference product: aiapply.co

Since 2026-10-08 (ADR-017) the product aims to stay **as close as possible to
[aiapply.co](https://aiapply.co)** in what it offers and how a person uses it.
This page is the working comparison. Check it before designing a feature, and
update it whenever either side changes.

## How reliable this page is

On 2026-10-09 the owner supplied a saved copy of the aiapply.co landing page (HTML and
PDF). The development sandbox cannot reach the site itself, so **the landing page and the
FAQ data embedded in it are the checked source**. They are marketing copy: they say what
AIApply claims to offer, not how it behaves.

Still unseen: the app itself, price amounts (the page names none), which sites Auto-Apply
actually submits to, and anything behind the login. Those rows keep their third-party source and
say so. Third-party sources: [Scoutify](https://scoutify.com/blog/aiapply-review) ·
[Techjockey](https://www.techjockey.com/detail/aiapply) ·
[Jobright](https://jobright.ai/blog/aiapply-review-2026-how-it-works-pricing-and-honest-user-experiences/) ·
[Trustpilot](https://nl-be.trustpilot.com/review/aiapply.co) ·
[Jobscan](https://www.jobscan.co/blog/jobscan-vs-aiapply/) (a competitor: weigh it accordingly).

**Corrections to the first version of this page** (2026-10-08, third-party only):

- Job board size: "about 600k jobs, 20+ countries" was wrong. The page claims **20M+ live
  jobs** (company careers pages about 7.6M, job boards about 6.1M), "thousands of sources daily".
- "No public API" was wrong: the footer lists an **AutoApply API** (also White Label,
  For Career Coaches, Affiliate, Hire Talent, Human Data Labs). What it offers is not on the page.
- The page does **not** name LinkedIn, Indeed or Glassdoor as job sources or apply targets.
  That came from third parties and stays unconfirmed.
- A **Resume Scanner** exists (the `?` row), and so do a Resume Translator, a LinkedIn-to-Resume
  importer and a Mock Job Interview tool.
- "Auto" and "Human-in-the-Loop" are third-party names. The site says you "can review drafts
  before they're sent", and a testimonial on it says "fully manual, hybrid, or full automation".
- Prices: none on the page. The "$29" from a directory listing is unverified.

## Parity matrix

Source: **site** = the saved landing page · **3rd** = third-party only.
Status: **have** = works today · **added** = built with ADR-017 · **partial** ·
**gap** = not built · **differs** = deliberately not the same (reason below).

| AIApply offers | Source | Here | Status |
|---|---|---|---|
| Set role, location and salary preferences; build or import a resume (PDF/Word upload) | site | `profiles/<id>/profile.yaml`, `01-knowledge/05-job-match.md`, CV cards; `add-profile` skill. File-based; a form is P5 | have |
| "LinkedIn to Resume": import a LinkedIn profile into a CV | site | LinkedIn export is kept in `02-sources/`; nothing converts it | gap |
| Job board: 20M+ live jobs from thousands of sources; apply or auto-apply with a click | site | Remotive, Arbeitnow, Adzuna, JSearch (an API that itself aggregates the large boards), ATS boards planned. No in-app board: the digest email is the feed; `apply approve` is the click | partial |
| Auto-Apply: sources matching listings, tailors the documents, submits; you can review drafts before they are sent; progress tracked in the dashboard | site | `apply.mode: auto` behind `authorization.yaml` (switch plus dated acknowledgement), caps, adapters for Greenhouse, Lever, Ashby; `assisted` fills and you click submit; the summary tracks progress | have |
| Manual, hybrid or fully automatic (a testimonial's words) | site | `manual`, `assisted`, `auto` | have |
| Auto-Apply on LinkedIn, Indeed, Glassdoor, career pages | 3rd | Needs an adapter per site (see "How to unblock"); the gate in `authorization.yaml` is already open | gap |
| Auto-Apply credits, sold in packs (for example 100 or 250), separate from Premium | site | Per-day and per-week caps in `config.yaml → apply.auto`. Billing and a usage ledger are P4 / P6 | partial |
| Free limited tier; Premium monthly or annual; student discount; cancel any time; refunds case by case | site | One owner, no plans. Hypothesis in `PRODUCT.md` | gap |
| Application Kit: job-specific cover letter, tailored resume and follow-up email | site | `jobscan.kit`: per job a tailored summary, what to emphasise in the chosen CV, honest gaps, cover letter, follow-up email | **added** |
| Cover-letter tone (Formal, Proactive, Concise); regenerate sections; PDF or Word export; templates; several versions kept | site | Tone and regeneration happen by chat; the `cv-tailoring` skill produces the Word file; no templates | partial |
| Application tracking | site | `apply track`, funnel, "in progress" and "follow up" in the daily summary | **added** |
| AI Mock Interview / Interview Practice: role-specific questions, instant feedback | site | The kit's `interview-prep.md`: likely questions with outlines grounded in your CV, and questions to ask. No scored mock interview | partial |
| Interview Buddy: live coaching during interviews, real-time answer suggestions through an earpiece or screen, post-interview feedback | site | Not planned (see below) | differs |
| Resume Scanner and Optimizer: ATS check with keyword fixes | site | The kit's `gaps` is the nearest thing | gap |
| Resume Translator | site | The kit writes the letter, follow-up and summary in any language the profile speaks at working level; translating the CV file is by hand | partial |
| Share a secure resume link that can be disabled | site | Needs a web service (P5) | gap |
| Link view tracking | 3rd | Needs a web service (P5) | gap |
| AutoApply API, White Label, For Career Coaches, Affiliate, Hire Talent | site | Not relevant to a one-owner tool | differs |
| Data encrypted at rest and in transit, not sold, deletable | site | Private repo; the CV text and answers stay in `career-data` | n/a |
| Answers to application questions (Auto-Apply fills forms) | 3rd | Unknown required questions are logged, drafted by the model from your CV cards, and used only after you approve each one: `apply questions` | **added** |

**Marketing claims on the page, not verified:** 2,064,348 users, 61% get an interview in the
first 10 days, 372,241+ roles applied to, 4.8/5 from 850 ratings (page data; Trustpilot shows about
4.2).

**Here but not on AIApply's page:** `jobscan.clip` (bring any job you found yourself into the
scan), honest `gaps` in every kit, a language prefilter, the company blacklist enforced three
times, and a human approval for every drafted form answer.

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
   legal or work-authorisation questions unless the owner wrote the answer. The owner
   confirmed on 2026-10-09 that removing those entries from `authorization.yaml` was
   intended; the code still hands CAPTCHAs and those questions to the human.
5. **No live interview copilot.** Interview Buddy answers in real time during the interview,
   which needs a live audio client and puts the tool's words in the candidate's mouth. This
   product prepares the candidate instead.
6. **Review before sending is the default**, not an option you find after the first
   bad batch. `manual` is still the shipped mode.

## Not built blind

LinkedIn, Indeed and Glassdoor adapters (reading listings, Easy Apply) are allowed by
ADR-017 but cannot be written from the development sandbox: it cannot reach those sites, so any
selector would be a guess, and a wrong guess on a logged-in account is how accounts get
restricted. JSearch already returns listings from the same boards through a licensed API, and
`jobscan.clip` takes any single posting you find yourself. What neither can do is apply.

## How to unblock the rest

The adapters can be built in the Claude cloud from pages **you** save and upload. The exact
steps, per site and per page, are in [`CAPTURING-PAGES.md`](CAPTURING-PAGES.md). In short:

| Gap | What it needs from the owner | Then |
|---|---|---|
| Test `clip` on a real page | Save one job page per site, run `jobscan.clip --dry-run` | It prints the posting, or says the page carries no `JobPosting` data |
| Reading search pages | One saved results page per site, logged out, through `jobscan.redact` | Parser written and tested against a synthetic fixture built from it |
| Easy Apply and other site forms | The dialog's HTML for each step, through `jobscan.redact`, stopping before Submit | Adapter written against synthetic fixtures; you run `apply run --dry-run --headed` once and paste back `apply bundle`; I fix; repeat |
| Scored mock interviews | Nothing: seed a Claude chat with `interview-prep.md` | None |
| Live audio, server-side submission | A decision and, for submission, a lawyer's read of the ATS terms | Not started |

## Keeping this page honest

- When a feature ships, move its row to **added** and link the code or doc.
- When the aiapply.co page changes, save it again and re-read the FAQ data (it is the
  `FAQPage` JSON-LD block, which holds the full answers).
- When the two products diverge for a reason, add it to "Where it deliberately differs"
  instead of leaving a silent gap.
