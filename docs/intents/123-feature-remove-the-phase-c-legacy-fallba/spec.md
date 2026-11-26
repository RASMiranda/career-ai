# Spec: remove the phase C LEGACY fallbacks and fix the decide install template (#123)

Inputs: `intent.md`, the owner's answers on #124 (precondition waived for the decide-link test; refuse to run on a
stale root; faillog root rule dropped; `ConfigError` for no profile; guard in `load_config`; stale means non-empty;
ADR-077 to be recorded by a human). The names in the intent were checked against the code and exist
(`layout.moved_path`, `MOVED_FOLDERS`, `MOVED_FILES`, `_warned`, `pipeline.PUBLISH_PATHS`/`publish_paths`,
`apply/policy.apply_cfg`, `apply/faillog`).

## Requirements

1. `layout.moved_path(root, rel, pid)` returns `root/profiles/<pid>/<rel>` for every name, moved or not. It never
   returns a root path. `MOVED_FOLDERS`, `MOVED_FILES`, `_warned`, `_legacy_unit` and the warning are deleted.
2. `moved_path` with `pid` None uses the only profile; with several profiles it raises `ConfigError` (as
   `default_profile`). With no profile folder it raises `ConfigError`. `moved_name` follows.
3. `layout.apply_path` loses its "no profile folder keeps the root" branch and raises `ConfigError` like
   `default_profile`. `moved_path` may then delegate to `resolve`. Callers and tests that relied on the root
   location are updated.
4. `config.load_config` raises `ConfigError` when any of root `reports/`, `state/`, `applications/` holds a
   file or folder, or root `logs/runs.jsonl` is a non-empty file. An empty folder or empty file does not
   count. The message names the stale path and the profile path to move it to, in the same shape as the
   stale `authorization.yaml` error (ADR-075 d). One helper builds both messages. Because every command loads
   config, `validate` and `collect --preflight-only` get the same error.
5. `pipeline.PUBLISH_PATHS` / `publish_paths` yield only `profiles/<id>/reports`, `profiles/<id>/state` and
   `profiles/<id>/applications/queue.json`, per profile. No root form. `publish` refuses a root `reports/`,
   `state/` or `applications/queue.json` in the index with the existing refusal path.
6. `apply/policy.apply_cfg` merges `DEFAULTS` with the profile's `apply_config` only. It never reads
   `cfg["apply"]`; `_warned_root_apply` and the warning are deleted. A profile without `apply/config.yaml` gets
   the defaults. An unknown `pid`, or several profiles with `pid` None, raises `ConfigError`, not a silent default.
7. `apply/faillog` has no root `logs/apply/` path: resolution requires a profile folder (`ConfigError`
   otherwise), and `read_since` with no profile reads every profile's folder only. A failure line with no known
   profile is still skipped with one warning, never written to the root. The ADR-020 failure email still goes out.
8. `docs/decide-workflow.yml` stages `git add -- 'profiles/*/applications/queue.json'` and nothing else changes in
   it. `.github/workflows/decide.yml` is not touched (not in this repo, protected).
9. A test checks that the template and the installed `decide.yml` differ only in the paths they name (see
   Concerns, 3).
10. Docs and docstrings: `layout.py`, `pipeline.py`, `faillog.py`, `policy.py`, the `apply/cli.py` comment at
    line 182, `docs/ARCHITECTURE.md` and the data README text in this repo describe only the profile layout.
    After the change `grep -rn "LEGACY" src` matches only `applylog.py` (`LEGACY_FIELDS`, `LEGACY_FILE`).

## Acceptance criteria

1. Given a profile-layout data repo, when `moved_path` resolves `state/job-scan-seen.json`, `reports/<day>.md`,
   `applications/queue.json` or `logs/runs.jsonl`, then it returns the path under `profiles/<id>/`, and stderr has
   no output containing "LEGACY".
2. Given a non-empty root `reports/`, `state/` or `applications/`, or a non-empty root `logs/runs.jsonl`, beside the
   profile folder, when any command calls `load_config`, then it fails with `ConfigError` naming the root path and
   the profile path, and nothing is read or written.
3. Given empty root `reports/`, `state/`, `applications/` folders, when `load_config` runs, then it succeeds.
4. Given the index holds `reports/x.md`, `state/x.json` or `applications/queue.json` at the root, when `publish`
   runs, then it refuses and commits nothing; given only allowlisted `profiles/<id>/` paths, it stages them.
5. Given a profile with no `apply/config.yaml` and a root `config.yaml` with an `apply:` section, when apply
   settings load, then the defaults apply, the root section has no effect and no warning is printed.
6. Given a data repo with no profile folder, when `moved_path`, `apply_path` or the faillog resolves a path, then
   `ConfigError` is raised.
7. Given a failed job of profile `rui` and a stale `logs/apply/` at the root, when `read_since` runs, then only
   `profiles/rui/logs/apply/` lines are returned.
8. Given `docs/decide-workflow.yml`, then it contains `git add -- 'profiles/*/applications/queue.json'` and not
   `git add applications/queue.json`.
9. Given the template and an installed `decide.yml` that name the same paths, when the comparison test runs, then
   it passes; given a difference outside path names, it fails.
10. Given the change, `grep -rn "LEGACY" src` finds only the applylog names and `python -m pytest -q` passes.

## Non-goals

- Item 7 of the issue (data repo `.gitignore` line `logs/apply/screens/`): a human data-repo change.
- `authorization.yaml` stage 2 and its root-file refusal (ADR-075 d): separate PRs.
- Editing `.github/workflows/decide.yml`, `docs/DECISIONS.md` or the data repo.
- Any change to scoring, submission, answer approval or the failure email content.
- A migration tool for an old data repo: it stays unsupported.

## Concerns flagged

1. **ADR-077 is not yet recorded.** It must cover the end of the LEGACY window (ADR-075 c), the stale-root guard
   (non-empty) and the dropped faillog root rule. I cannot edit `docs/DECISIONS.md`; a human records it.
2. **Rollback is gone.** The decide-email link was never tested on the moved layout (waived by the owner on #124).
   After merge there is no code rollback; a failure gets a new issue and a forward fix. ADR-075 (c) intended the
   fallback as the rollback until then.
3. **The installed `decide.yml` is not in this repo.** `.github/workflows/` here holds no `decide.yml`; it lives in
   `career-data`, which agents must not read. Req 9 therefore needs the installed file's location as an input,
   for example an environment variable pointing to a copy (test skipped when unset), or a fixture copy of the
   path lines. The plan stage must choose; a skipped test is a weaker check than the owner asked for.
4. **Guard in `load_config` is wide.** `validate` and `collect --preflight-only` also fail on a stale root, as the
   owner chose. Consistent with ADR-075 d. A data repo from before #70 stops working with this code (ADR-075
   consequences), as after ADR-070 and ADR-072.
5. **Publish allowlist (ADR-075 b)** stays explicit: never `profiles/` as a whole, `logs/`, `answers.json` or
   identity files. Req 5 only removes root entries and widens nothing.
6. **ADR-003, ADR-007, ADR-017 to ADR-022:** no conflict. Nothing gives the model a new action; the guard and
   allowlist stay deterministic code.
7. **`apply_path` change (req 3)** goes slightly beyond the issue's code items, because its root branch is the same
   two-answers problem the owner removed for faillog. Drop req 3 if the owner wants a narrower change.

## Test plan

- `tests/test_layout.py`: replace the LEGACY tests with profile-only tests (AC 1, 6); several-profile error for
  `moved_path`; no stderr output.
- `tests/test_profiles.py` (or a new `tests/test_stale_root.py`): the `load_config` guard (AC 2, 3), including the
  message shape shared with the stale `authorization.yaml` case.
- `tests/test_pipeline.py`: `publish_paths` lists only profile forms; `publish` refuses root forms in the index
  (AC 4).
- `tests/test_apply_core.py`: `apply_cfg` defaults with no profile config, root section ignored, no warning (AC 5).
- `tests/test_failure_email.py` and the faillog tests: only profile folders read; stale root ignored; failure email
  still produced (AC 7).
- New `tests/test_decide_template.py`: staging line present (AC 8) and the template/installed comparison (AC 9,
  see Concern 3).
- Update every existing test and fixture that builds a root-layout data repo to the profile layout.
- Final: `grep -rn "LEGACY" src` and `python -m pytest -q` (AC 10).
