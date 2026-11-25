# Plan: Move owner-specific data under profiles/<id>/ (phase C), issue #118

Source: `spec.md` (f392df8) plus the owner's review amendments 1-6 (binding; each is placed below as **[Am n]**). I read only `career-ai`. The tech-lead and scrum-master subagents were not run (turn budget); I wrote their parts, so a human should check sizing and the security section.

## Sizing (scrum-master part)

Too big for one reviewable PR. Four career-ai PRs, in this order, with the data work between them:

| PR | Repo | Content | Merge gate |
|---|---|---|---|
| **1** | career-ai | Stage 1 code: layout, `LEGACY` read-and-write fallback, publish allowlist + staged check, `decide --profile`, faillog, apply config, tests | tests green |
| **D1** | career-data | Renames only, `decide.yml`, drop `logs/apply/.gitkeep` (human-only) | routine paused; no browser-apply after this |
| **2** | career-ai | Cleanup: remove `LEGACY` and the root allowlist entries; grep check (A12) | D1 merged |
| **3 + D2** | both | Stage 2: `authorization.yaml` under the profile, no fallback, fails closed | routine paused for this step only |

PR 1 may split into 1a (layout + LEGACY + writers, R1-R12, R17) and 1b (publish allowlist, staged check, `decide`, R13-R16), if the diff passes ~600 lines.
Human-only (protected paths, ADR-024/025): the new ADR (`docs/DECISIONS.md`), `decide.yml`, routine prompt/trigger, `authorization.yaml` and `config.yaml` moves, all career-data PRs, the server-side control.

## Files that change (and why)

Source references found by grep (spec list was a start, C10):
- `layout.py`: docstring and `apply_path` lose "stay at the root"; add the `LEGACY` resolver (profile path wins if it exists, else an existing root file is read **and written in place** with one warning, else the profile path is created) **[Am 2]**. PR 2 deletes it.
- `apply/queue.py:28`, `apply/answers.py:88`, `apply/runlog.py:15`, `apply/slug_cache.py:19`, `apply/linkedin.py:27`: build paths via `layout`.
- `state.py:30,51,80`, `collect.py:43`, `report.py:196-197`, `apply/cli.py:312-313` (applications.md): same.
- `apply/faillog.py:61`: take the profile from the queue row; no row means skip with a warning, never the root (R6).
- `config.py:58-69`: read `profiles/<id>/apply/config.yaml`; root `apply` ignored after PR 2. `load_authorization` moves in PR 3.
- `pipeline.py:29,45-51,78-83`: allowlist and staged-path check; PR 3 for auth.
- `decide.py:55,66-71`: `--profile` (default the only profile, error for several), queue through `layout` **[Am 3]**.
- PR 3 only: `validate.py:86`, `report.py`, `apply/authz.py`, `apply/policy.py`, `bank.py:278`, `apply/cli.py:173`, `config.py:69`, `pipeline.py:78-83`.
- `kit.py:171,246,320`: only the printed hint names `applications/`; update the text. Its paths already use `profiles/`.
- Docs: data README text and ADR-071 (c) wording (created on first use; scan history is `state/runs.jsonl`) go into the human ADR; `layout.py` docstring in PR 1.
- Tests: `test_layout`, `test_pipeline`, `test_apply_core`, `test_answers`, `test_store`, `test_linkedin_easy_apply`, `test_guard`, `test_profiles`/`test_doctor`, blacklist/kit/clip fixtures, goldens only where a moved path is named.

## Order of work

1. Tests first (failing), per the Proof list. 2. `layout` + `LEGACY`. 3. Writers/readers one module at a time. 4. Allowlist + staged check. 5. `decide`. 6. Suite. Then D1, PR 2, PR 3/D2.

## Publish allowlist **[Am 1, Am 4]**

- PR 1: allowlist is per profile: `profiles/<id>/reports`, `profiles/<id>/state`, `profiles/<id>/applications/queue.json`, **plus** the three root paths (`reports`, `state`, `applications/queue.json`) while `LEGACY` exists. Test: root and profile forms accepted, anything else refused. Never `profiles`, `profiles/<id>`, `logs`, `answers.json`. Dropping `logs` from the old tuple is deliberate.
- PR 2 removes the root entries.
- The staged-path check guards `pipeline`'s own bugs only; it does not stop a routine that runs `git` directly (same as the old rule). State this in the ADR and the code docstring.
- Human follow-up in career-data (to verify): a server-side control. Candidates: a CI check failing pushes by the routine's identity outside the allowlist; CODEOWNERS on `answer_bank.yaml`, `profile.yaml`, `authorization.yaml` (needs branch protection and a private-repo plan that supports it); rulesets with path restrictions (plan-dependent). None confirmed.

## Pause scope **[Am 6]**

Routine paused only while D1 is open and for stage 2 (PR 3/D2). The `LEGACY` window plus allowlist (a) keeps it safe from PR 1 merge. No browser-apply run between D1 and PR 2. `decide.yml` also waits for D1.

## Risks

- Routine write access under `profiles/` (C2): reviewers read R13-R15 and A4/A5 closely; security-reviewer on PR 1.
- Split seen-set if LEGACY read and write diverge: covered by the write-where-you-read test.
- Per-profile budget and dedup (accepted C5); many test fixtures change (C6).
- A stale root `authorization.yaml` must never be read (PR 3): test with an unreadable file.
- `answers.json` accidentally staged: the single-file `queue.json` entry plus the staged check.

## Proof

New tests, written first:
- `test_layout`: new names under the profile; LEGACY read **and write in place** with one warning; profile wins when both exist; after PR 2 no root read.
- `test_pipeline` (real `git init`): no `profiles`/`profiles/<id>` entry (A5); each forbidden name staged is refused, exit non-zero, nothing committed (A4); allowed publish lands under the profile (A2); two profiles each publish only their own (A3); root+profile forms accepted in PR 1.
- LEGACY write test: seen-set updated at the root when only the root exists; no profile copy appears.
- `test_store`/`test_apply_core`/`test_answers`: queue, answers, run log, slug cache, cooldown; faillog under the profile and without a row skipped (A7); `apply failures` reads there.
- Apply config read from the profile; root `apply` ignored after PR 2 (A8).
- `decide --profile`: default single, error for several, queue via `layout`.
- `applylog check --strict` fixture counts unchanged (A11).
- PR 3: missing auth stops `prepare` "nothing was run" and `apply run --mode auto` refuses (A9); stale root file refuses, content unread (A10).
Checks: `python -m pytest -q` including `tests/test_no_personal_data.py` (A13); `grep` of `src/` for root builds of moved files, run after PR 2 (A12).

## Tasks

- [x] PR 1b tests (run 1, per P3): allowlist, staged check, `decide --profile` (written, not run). The other PR 1 tests wait for run 2
- [x] `layout`: LEGACY resolver (read+write in place, one warning), docstring (run 2)
- [x] Queue, answers, runlog, slug cache, cooldown via `layout` (run 2; `cmd_run` uses `moved_name`)
- [x] State files, `collect`, reports, apply summary via `layout` (run 3; `pid` optional, per-profile dedup inside `collect` not yet); run 4 adds `--profile` to `collect`, `report`, `apply run` and `clip` (`Seen`, `Budget`, `Journal`, `Queue`, run log by profile)
- [ ] `faillog` with the profile from the queue row
- [x] Apply config from `profiles/<id>/apply/config.yaml` (run 5a; root `apply` section is the LEGACY fallback with one warning)
- [x] `pipeline` passes `--profile` to `collect` and `report` (run 5a)
- [x] `PUBLISH_PATHS` per-profile allowlist (+ root while LEGACY) and staged-path check (run 1)
- [x] `decide --profile` (run 1; the queue itself moves through `layout` in run 2, with `Queue`)
- [ ] `kit.py` hint text; update fixtures and goldens only where paths are named
- [ ] Suite green; open PR 1
- [ ] Human: ADR, D1 (renames, `decide.yml`, drop `.gitkeep`), pause routine
- [ ] PR 2: remove LEGACY and root allowlist entries; grep check
- [ ] Human: server-side control in career-data (verify the feature)
- [ ] PR 3 + D2: `authorization.yaml` move, fail closed, A9/A10
