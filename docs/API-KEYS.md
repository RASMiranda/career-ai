# API keys: where they come from and how they are set

No key ever lives in a repo, a file or a chat. Two job sources need one:

| Source | What the code needs | Where it comes from | How it reaches the code |
|---|---|---|---|
| Adzuna | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Adzuna developer portal | environment variables (the key goes in the request URL) |
| JSearch (RapidAPI) | the `X-RapidAPI-Key` header | RapidAPI | an **API credential** that the environment adds to the request (the code never sees the key) |

Remotive and Arbeitnow are public and need nothing.

Why two mechanisms: JSearch authenticates with a header, so it can use the environment's
credential proxy, which keeps the key out of the routine's shell (ADR-007, ADR-015).
Adzuna authenticates with URL parameters, which a header cannot carry, so it uses plain
environment variables.

## 1. Getting the keys

### Adzuna
1. Sign in at <https://developer.adzuna.com> and open
   <https://developer.adzuna.com/admin/access_details>.
2. Under *Application* (the default app created at signup):
   - **Application ID** (a short code) is `ADZUNA_APP_ID`.
   - **Application Keys** lists the key: that is `ADZUNA_APP_KEY`.
     Use **Create new key** to make a fresh one, then delete the old one.
3. *Plan* shows the limits (Trial Access). `budgets.adzuna` in `career-data/config.yaml`
   must not exceed them.

### JSearch
1. On RapidAPI open the JSearch API (provider *letscrape*), subscribe to a plan (the free
   one is enough), and open its **Playground**:
   <https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch/playground/>
2. In the playground's *Authorization* panel the value shown for **`X-RapidAPI-Key`** is
   the key. Copy it from there.
3. `budgets.jsearch` in `config.yaml` must not exceed the plan's monthly requests.

## 2. Setting them in the Claude environment

The routine runs in the cloud environment **`career-scan`**. Open its settings from the
routine's edit screen (the environment chip under the instructions box), or from the
cloud-environment menu in the title bar of a session that uses it, then **Edit**. The panel
has four sections. Only sessions started **after** you save see the change.

### Network access
Choose **Custom** and add under *Allowed domains*:
- `api.adzuna.com`
- `jsearch.p.rapidapi.com` (the JSearch credential in the next step normally adds its own
  allow rule; add it here if JSearch reports `ConnectionError`)

Keep the default package-manager list: the setup script needs it.

### API credentials → Add credential (JSearch)
| Field | Value |
|---|---|
| Add to | `career-scan` |
| Name | `JSearch RapidAPI` |
| Credential type | a custom-header / API-key type if the dropdown offers one; otherwise `Bearer` and rename the header row as below |
| Allowed websites | `jsearch.p.rapidapi.com` |
| Path prefixes | *(empty)* |
| Custom headers (one row) | Name `X-RapidAPI-Key`, Prefix *(empty)*, Value *the RapidAPI key* |

No `Authorization` header and no `X-RapidAPI-Host`: the code sends the host header itself.
Values cannot be viewed after saving, so to change one, delete the credential and re-add it.
`config.yaml → sources.jsearch` has `auth: proxy`, which tells the code not to look for
`RAPIDAPI_KEY`.

### Environment variables (`.env` format, one per line, no quotes or spaces around `=`)
```
PYTHONPATH=src
ADZUNA_APP_ID=<Application ID>
ADZUNA_APP_KEY=<Application Key>
```
The panel warns that these are visible to anyone using the environment. That is why only the
Adzuna values are here: a free, read-only job-search key that can be regenerated at any time.

### Setup script
```bash
#!/bin/bash
pip install "PyYAML>=6.0"
```

Finish with **Save changes**.

## 3. Checking that it works

In a session of the `career-scan` environment started after saving:

```bash
cd career-ai && python -m jobscan.doctor --data ../career-data
```

It makes one real request per source (one request of each monthly quota), prints only
statuses, never a key, and exits 1 if anything fails:

```
adzuna   OK, HTTP 200, 1 result(s) returned
jsearch  OK, HTTP 200, 1 result(s) returned [key added by the credential proxy]
```

| Output | Meaning and fix |
|---|---|
| `NOT SET: ADZUNA_...` | The variables are missing, or the session started before you saved them. Add them and start a new session. |
| `HTTP 401/403` | Key rejected, the plan is not subscribed, or (JSearch) the credential's host, path or header name does not match section 2. |
| `HTTP 429` | Monthly quota or rate limit reached. |
| `cannot reach the host` | The host is not under Network access → Allowed domains. |

During a scan the same problems show up as `jsearch: ConnectionError` or
`adzuna: ConnectionError` in the run's errors, and spend no budget. The weekly queries (the
only ones that use these two sources) run on `weekly_day` (Monday).

## 4. Rotating a key
Create the new key at the provider, update the environment (variable, or delete and re-add
the credential), delete the old key at the provider, then run the check above. If a key was
ever pasted into a chat, an issue or a file, rotate it: treat it as exposed.
