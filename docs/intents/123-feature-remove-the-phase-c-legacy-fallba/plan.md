# Plan: remove the phase C LEGACY fallbacks and fix the decide install template (#123)

Inputs: `spec.md`, the owner's answers on #124 (fixture always runs; `apply_path` root branch dropped; list every
`apply_cfg` caller; subagent parts stated). ADR-077 and the data repo `.gitignore` line stay with a human.

**Who wrote what.** The technical shaping below comes from a `tech-lead` subagent run in this stage, and the sizing
from a `scrum-master` subagent run in this stage. I merged both and checked the code names myself. **No human has
reviewed either part.**

## Size (scrum master)

M to L: about 600 to 800 changed lines, roughly 450 of them tests. The source change is 150 to 200 lines. Split in
two PRs, in this order, so `main` stays green after each:

- **PR 1, remove the fallbacks:** Tasks 1 to 8 and 10 to 11 (layout, publish, `apply_cfg`, faillog, `cli.py`,
  test conversion, docs).
- **PR 2, the guard and the template:** Tasks 9 and 12 (`load_config` stale-root guard, `docs/decide-workflow.yml`,
  fixture and comparison test). It only adds a refusal, so it goes second: with the tests already on the profile
  layout, the guard cannot break an unconverted test.

Never put the guard first, and never split by test file: removing the fallback turns unconverted tests red at
once. If the owner prefers one PR, treat it as L. Nothing in the spec is dropped by the split.

## Files that change (and why)

| File | Change |
|---|---|
| `src/jobscan/layout.py` | Delete `MOVED_FOLDERS`, `MOVED_FILES`, `_warned`, `_legacy_unit`, the warning and the `sys` import. `apply_path` loses its root branch: `resolve(root, pid or default_profile(root), rel)`, so no profile folder is a `ConfigError`. `moved_path` delegates to `apply_path` (keeps `_check_rel`). `moved_name` stays. Docstrings describe only the profile layout. |
| `src/jobscan/config.py` | `load_config`: stale-root guard and one message helper (PR 2). |
| `src/jobscan/pipeline.py` | `PUBLISH_PATHS` / `publish_paths`: profile forms only. Docstring. Root forms are then refused by the existing allowlist check. |
| `src/jobscan/apply/policy.py` | `apply_cfg` merges `DEFAULTS` with the profile's `apply_config` only. Delete `_warned_root_apply`, the warning, and `sys` if unused. Unknown pid, or several profiles with pid None, raises `ConfigError`. |
| `src/jobscan/apply/faillog.py` | `_dir`: no profile folder raises `ConfigError`; unknown profile still returns None (skip with one warning). `read_since(None)` reads profile folders only. Docstrings. |
| `src/jobscan/apply/cli.py` | Comment at line 182. Line 313 gets a pid (see callers). |
| `docs/decide-workflow.yml` | Staging line becomes `git add -- 'profiles/*/applications/queue.json'`. Nothing else changes. |
| `tests/fixtures/decide.installed.yml` | New. A copy of the installed `decide.yml` (see Risks 6). |
| `docs/ARCHITECTURE.md`, data README text in this repo | Remove root paths and LEGACY wording. |
| tests | See Proof. |

Not touched: `.github/**`, `docs/DECISIONS.md`, `career-data`, `authorization.yaml`, any `profile.yaml`.

## `apply_cfg` callers that change behaviour

`apply_cfg(cfg, pid)` now raises `ConfigError` for an unknown pid, and for `pid` None with zero or several profiles.
Callers let it propagate; the CLI's top level already reports `ConfigError` and exits non-zero.

| Caller | Pid passed | New behaviour | Test |
|---|---|---|---|
| `apply/cli.py:88` (`cmd_enqueue`) | each `p["id"]`, always known | No change. | existing enqueue tests, converted |
| `apply/cli.py:102` | `c.get("profile")`, None for an old row | One profile: uses it. Several profiles and a candidate with no profile: `ConfigError`, run stops. `Queue(root)` at `:95` raises first with several profiles, so a per-row skip would not help. | new: enqueue with two profiles and a candidate with no profile exits with `ConfigError` |
| `apply/cli.py:169` (`cmd_run`) | `args.profile`, may be None | One profile: uses it. Several profiles and no `--profile`: `ConfigError` (the queue at `:183` already needs it). | new: `cmd_run` with two profiles and no `--profile` |
| `apply/cli.py:313` (`cmd_summary`) | none | Pass `getattr(args, "profile", None)`, as `cmd_run` does. One profile: unchanged. Several without `--profile`: `ConfigError`, as `Queue(root)` at `:312` already does. | new: summary with one profile works; with two and no `--profile` errors |
| `report.py:140` | `pid` of the profile in the loop | Known pid, no change. | existing report tests, converted |

Also check that no test passes a pid missing from `cfg["profiles"]`, and that none calls `apply_cfg(cfg)` on a cfg
with zero profiles.

## Order of work

PR 1:
1. Write the failing tests (Proof, PR 1 list).
2. `layout.py`.
3. `pipeline.py`.
4. `policy.py`, then the `apply_cfg` callers in `cli.py`.
5. `faillog.py`.
6. Convert the root-layout tests. Look first for a shared helper (`conftest.py`, a `make_root`): one change may fix many.
7. Docs and docstrings; `grep -rn "LEGACY" src`; `python -m pytest -q`.

PR 2:
8. Failing guard and template tests.
9. Guard in `config.py`.
10. Template line and the fixture.
11. Full suite.

## Risks

1. **No code rollback** after merge. The decide-email link was never tested on the moved layout (owner waived,
   accepted). A failure gets a new issue and a forward fix.
2. **Import cycle.** `layout.py` imports `config.py`, so the guard in `config.py` must not import `layout`. Use
   `cfg["profiles"][i]["id"]` and `Path` checks only.
3. **Inline profiles** (`profiles:` in `config.yaml`, no folder) have no profile folder, so they cannot use the moved
   files. Add a test that this gives the `ConfigError` from `moved_path`, so it is a stated outcome.
4. **Guard breadth.** `validate` and `collect --preflight-only` also fail on a stale root (owner choice). "Empty"
   means: a folder with no entries (`iterdir()`), a file of size 0. A `.gitkeep` makes a folder non-empty.
5. **faillog read with no profile folder.** Spec criterion 6 says the faillog resolution raises; a read on an empty
   repo should not crash the failure email. Plan: `write` raises `ConfigError` when no profile folder exists;
   `read_since` returns `[]`. **A human confirms this reading.**
6. **Fixture drift.** Agents cannot read `career-data`. The fixture is a hand-built copy of the installed file's
   structure with the path lines, so it can drift. The developer adds a header comment saying it mirrors the installed
   file, and the PR description must say: **refresh `tests/fixtures/decide.installed.yml` whenever the installed
   `decide.yml` changes.** A human should replace it with the real file before merge if possible. The test is
   always-run, with no environment variable and no skip.
7. **Stale `authorization.yaml` message does not exist in code yet** (stage 2 is a non-goal). The helper is built for
   the guard and is shaped so stage 2 can reuse it; the "one helper for both" check is deferred.
8. **ADR-077** is not written. It is a human step in `docs/DECISIONS.md`. ADR-075 (b), ADR-003, ADR-007 and ADR-017
   to ADR-022: no conflict (the allowlist only gets narrower; no new model action).
9. **Test churn.** About 7 to 9 files hold root-layout setups (`test_layout.py` about 42 hits, `test_store.py`,
   `test_pipeline.py`, `test_apply_core.py`, `test_blacklist.py`, `test_linkedin_easy_apply.py`, `test_clip.py`,
   `test_applylog.py`, faillog and failure-email tests). Convert them to the profile layout. Never weaken an
   assertion to make one pass.

## Proof

New tests, written first and seen failing:

PR 1
- `test_layout.py`: `moved_path` returns the profile path for `state/job-scan-seen.json`, `reports/<day>.md`,
  `applications/queue.json`, `logs/runs.jsonl`, even when a root copy exists; stderr (capsys) has no "LEGACY";
  several profiles without pid raise; no profile folder raises for `moved_path` and `apply_path`; `..` and absolute
  names are still rejected; `MOVED_FOLDERS`, `MOVED_FILES` and `_warned` no longer exist.
- `test_pipeline.py`: `publish_paths` lists only `profiles/<id>/{reports,state,applications/queue.json}`; `publish`
  refuses `reports/x.md`, `state/x.json`, `applications/queue.json` at the root and commits nothing; allowlisted
  profile paths are staged.
- `test_apply_core.py`: no `apply/config.yaml` plus a root `apply:` section gives the defaults, no warning; unknown
  pid and several profiles with pid None raise `ConfigError`; the callers table tests above.
- faillog tests and `test_failure_email.py`: with a stale root `logs/apply/`, `read_since` returns only profile
  lines; the failure email is still produced; a line with no known profile is skipped with one warning and written
  nowhere; no profile folder raises on write.

PR 2
- Guard tests (`tests/test_stale_root.py`): non-empty root `reports/`, `state/`, `applications/` and non-empty
  `logs/runs.jsonl` raise `ConfigError` naming the root path and `profiles/<id>/...`; empty folders and an empty file
  pass; `validate` and `collect --preflight-only` fail the same way.
- `tests/test_decide_template.py`: the template contains `git add -- 'profiles/*/applications/queue.json'` and not
  `git add applications/queue.json`; a `compare` function (strips indentation, ignores only lines with a path) passes
  on template vs fixture and fails when a non-path line differs.

Checks to run at the end of each PR:
- `python -m pytest -q` (the `pytest` check on the PR is the evidence).
- `grep -rn "LEGACY" src` matches only `applylog.py` (`LEGACY_FIELDS`, `LEGACY_FILE`).
- `grep -rn "_warned_root_apply\|MOVED_FOLDERS\|MOVED_FILES" src tests` finds nothing.

## Tasks

PR 1: remove the fallbacks
- [ ] 1. Write the failing tests listed under Proof, PR 1.
- [ ] 2. `layout.py`: delete the LEGACY block, drop the `apply_path` root branch, delegate `moved_path`, update docstrings.
- [ ] 3. `pipeline.py`: profile-only `PUBLISH_PATHS` / `publish_paths`, docstring.
- [ ] 4. `policy.py`: `apply_cfg` profile-only, `ConfigError` on unknown or ambiguous pid, drop the warning.
- [ ] 5. `apply/cli.py`: pass the profile at line 313, fix the comment at line 182, check lines 88, 102, 169.
- [ ] 6. `faillog.py`: no root path, `ConfigError` with no profile folder, `read_since` profile folders only.
- [ ] 7. Convert the root-layout tests to the profile layout (look for a shared helper first).
- [ ] 8. `ARCHITECTURE.md`, README text, docstrings; run the `grep` checks and `python -m pytest -q`.

PR 2: the guard and the template
- [ ] 9. Write the failing guard and template tests, then add the guard and helper in `config.py` (no `layout` import).
- [ ] 10. `docs/decide-workflow.yml`: the staging line only.
- [ ] 11. Add `tests/fixtures/decide.installed.yml` with the mirror header; add the PR note to refresh it.
- [ ] 12. Run `python -m pytest -q` and the `grep` checks; in the PR description list what a human must do: ADR-077,
      data repo `.gitignore` line (item 7), install the new template, replace the fixture with the real file.
