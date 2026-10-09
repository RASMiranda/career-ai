# Capturing pages for LinkedIn, Indeed and Glassdoor

How to test `jobscan.clip`, and how to give the Claude cloud what it needs to build the
site adapters, without logging in from the cloud and without sharing anything personal.

The split (ADR-017): **you** save pages in your own browser; **the cloud** turns them into
parsers and adapters and tests them against synthetic copies; **you** run the result on your
own machine. Nothing in this flow logs in to a site from the cloud, and no credential leaves
your machine.

## The cloud can fetch public pages itself (ADR-021)

If the environment allows the sites, ask the cloud session to test `clip` and it will run
`python -m jobscan.fetchpage` on a few public, logged-out job and search pages, then `clip` on each.
One plain request per page with an honest User-Agent, no login, no cookies; the first block signal
(HTTP 403/429/999, a login or challenge page, a CAPTCHA) ends the run and it does not try again that day.

To allow it: in the cloud environment settings (the environment menu in the session's title bar,
then **Edit**), under **Network access** add these to **Allowed domains**, keeping **Allow package
managers** ticked, then start a new session (or tell the current one):

```
www.linkedin.com   www.indeed.com   www.glassdoor.com
```

Add the regional host you actually use too (for example `pt.indeed.com`, `pt.linkedin.com`,
`www.glassdoor.pt`). A site may still block a cloud address; then use Parts 1 and 2 below, in your own
browser. **Logged-in steps (Easy Apply) are never fetched from the cloud.**

Pages worth keeping, after `jobscan.redact`, are stored in `career-data/captures/<site>/` (private), so
later sessions reuse them without another upload. Passwords, cookies and tokens are never stored there.

## Setup, once, on your PC

```powershell
cd C:\path\to\career-ai
pip install -r requirements.txt
$env:PYTHONPATH = "src"          # PowerShell. On bash: export PYTHONPATH=src
```

`career-data` is assumed to be next to `career-ai` (`..\career-data`).

## Part 1: test `clip` (three files, five minutes)

Do this once per site. A private window keeps your logged-in view out of it.

1. **Open one job on its own page.** From a search, click the job title, then open it in its
   own tab. The address usually contains `/jobs/view/` (LinkedIn), `viewjob` (Indeed) or
   `/job-listing/` (Glassdoor). A page that is only a side panel next to the results will not work.
2. **Save it:** `Ctrl+S`, set "Save as type" to **Webpage, HTML Only**, name it `linkedin-job.html`
   (`indeed-job.html`, `glassdoor-job.html`). If step 4 says nothing was found, save it again as
   **"Webpage, Complete"**. Not "Single File (.mhtml)": that format is not read.
3. **Test it without writing anything:**
   ```powershell
   python -m jobscan.clip "$HOME\Downloads\linkedin-job.html" --data ..\career-data --profile rui --dry-run
   ```
4. **Read the result.**
   - `would clip  <title> — <company>` with the place, pay and a snippet of the text: this site
     works. Run it again without `--dry-run` to queue that job for the next scan.
   - `! the prefilter would discard it: …` is information, not an error: your own rules
     would drop that job.
   - `no schema.org JobPosting found in this page`: that page does not carry the data. Go to
     Part 2 and send me that page.

## Part 2: what to send so adapters can be built

Make every file safe first (`redact` removes scripts, session tokens, form values, query
strings, emails, phone numbers and every `--term` you give it), then check the result and
attach the `.redacted.html` files to the chat, as you did with the aiapply files.

```powershell
python -m jobscan.redact "$HOME\Downloads\linkedin-job.html" --term "YourFirstName" --term "YourLastName" --term "YourCity" --term "YourEmployer"
```

Open the `.redacted.html` in a text editor and search for your name, your email and your
phone number before you send it. Only what `redact` lists was removed.

| File | How to capture it | Logged in? |
|---|---|---|
| `<site>-job` | Part 1 | No (private window) |
| `<site>-search` | Search for something you would really search ("senior java developer", your country, remote), save the results page as in Part 1 | No |
| `linkedin-easyapply-1-contact`, `-2-resume`, `-3-questions`, `-4-review`, and `-error` | See below | Yes |
| The same for Indeed ("Apply now") and Glassdoor ("Easy Apply") | See below | Yes |

For each **application step**:

1. Open a job that has Easy Apply / Apply now and start the application.
2. When a step is showing, right-click inside the dialog and choose **Inspect**.
3. In the panel that opens, click up the tree until the highlighted area covers the whole
   dialog (the element with `role="dialog"`). Right-click it, **Copy → Copy outerHTML**.
4. Paste into Notepad, save as `linkedin-easyapply-2-resume.html`, then run `redact` on it.
5. Click **Next** to reach the following step and repeat. Include **one step that shows a
   required-field error** (press Next with a required box empty), and the **review** step.
6. **Stop before the final Submit button, and close the dialog without sending.**

Pick a job whose questions are varied: one of each kind (a text box, a dropdown, yes/no
buttons, a number, a checkbox) if you can find them. A handful of files per site is enough.
Stop at once if a site shows a CAPTCHA or an "unusual activity" notice, and tell me.

## What the cloud does with them

- Builds small **synthetic fixtures** (same tags, classes and labels, invented text) from your
  files for the tests in this repo, so the public repo never holds a real page.
- Writes the parsers and the `owner_browser` adapters, with the stop-at-first-block rule from
  ADR-017, and the tests.
- Does **not** log in, store credentials, or run anything against the real sites.

## Part 3: the loop on your machine

Once an adapter exists:

1. `pip install -r requirements-apply.txt` and `python -m playwright install chromium`, once.
2. Approve one real job you are happy to test with (`apply approve <key>`: the key is in the daily
   summary), then:
   ```powershell
   python -m jobscan.apply --data ..\career-data run --mode assisted --dry-run --headed
   ```
   It opens a visible browser, fills the form and never submits (`manual` mode, the default, runs
   nothing, hence `--mode assisted`). It waits for Enter before closing the browser. Anything it
   cannot do is logged, redacted.
3. `python -m jobscan.apply --data ..\career-data bundle --out failures.md`, then paste
   `failures.md` into the Claude cloud session. Nothing personal is in it.
4. I fix the adapter; you pull and run again. Repeat until a dry run is clean.
5. Submitting for real stays behind `authorization.yaml` (switch plus dated acknowledgement)
   and your own `config.yaml` opt-in for the source.

Questions the form asks that nothing can answer yet go through `apply questions` (see the README):
the model drafts, you approve each one.

## What this does not cover

LinkedIn's terms prohibit automated applying, and a restricted account is a real risk. That is
your decision, and it is why the adapters run only on your machine, visibly, slowly, and stop at
the first sign of a block (ADR-017).
