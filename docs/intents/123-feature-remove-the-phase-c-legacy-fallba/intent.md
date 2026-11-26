# Intent: remove the phase C LEGACY fallbacks and fix the decide install template (#123)

## Problem

Phase C (#118, ADR-075) moved the owner-specific data in the data repo under `profiles/<id>/`. The code still
carries the transition rules for it. `layout.moved_path` falls back to root `reports/`, `state/`, `applications/`
and `logs/runs.jsonl` and warns about LEGACY. `pipeline.PUBLISH_PATHS` still allowlists the three root paths.
`apply/policy.apply_cfg` still falls back to the root `apply` section. `apply/faillog` still reads the root
`logs/apply/`. The install template `docs/decide-workflow.yml` still stages the old queue path. While these
rules exist, a stale root copy can be read, written or published, and the code has two answers for where data lives.

## Proposed outcome

The profile folder is the only place the code looks, as ADR-070 and ADR-072 did for the earlier phases. Done is
items 1 to 6 of the issue:

1. `layout.moved_path` returns the profile path only. The folder-level LEGACY rule, `MOVED_FOLDERS`/`MOVED_FILES`
   fallback, `_warned` set and the warning are gone.
2. `pipeline.PUBLISH_PATHS` / `publish_paths` allowlist only `profiles/<id>/reports`, `profiles/<id>/state` and
   `profiles/<id>/applications/queue.json`.
3. `apply/policy.apply_cfg` reads only the profile's `apply/config.yaml`; defaults apply when it is absent.
4. `apply/faillog.read_since` no longer reads the root `logs/apply/`.
5. `docs/decide-workflow.yml` stages `git add -- 'profiles/*/applications/queue.json'`, the same as the data repo.
6. `docs/ARCHITECTURE.md`, the data README sections and the docstrings in `layout.py`, `pipeline.py` and
   `faillog.py` stop mentioning root paths or LEGACY.

Given/When/Then from the issue:

- Given a profile-layout data repo, when code resolves a moved name, then it gets the profile path, never the
  root, and no warning mentions LEGACY.
- Given a stale root `reports/`, `state/` or `applications/` beside the profile folder, when a scan, report,
  decide or apply run starts, then it is ignored (or stops with a clear error, as the spec decides) and is never
  read or written.
- Given the routine publishes, when the index holds a root `reports/`, `state/` or `applications/queue.json`,
  then `publish` refuses it.
- Given a profile with no `apply/config.yaml`, when apply settings load, then defaults apply and the root
  `apply` section is not read.
- `grep -rn "LEGACY" src` finds only the unrelated applylog legacy-outcomes names.
- The full suite passes, and the template and the data repo's `decide.yml` stage the same path.

## Affected users and systems

- The owner, who runs the scan routine, decide email links and `apply run`, and who installs the decide workflow.
- `src/jobscan/layout.py`, `pipeline.py`, `apply/policy.py`, `apply/faillog.py`, and their tests.
- `docs/decide-workflow.yml` (template), `docs/ARCHITECTURE.md`, and the data repo README.
- A checkout of `career-data` from before #70 stops working with this code, as after ADR-070 and ADR-072.

## Constraints

- ADR-070 and ADR-072: the same pattern, profile path only. This change follows them and does not reopen them.
- ADR-075: (c) says LEGACY is removed in a cleanup PR, which this is. (b) keeps the explicit allowlist for
  commits under `profiles/<id>/` (reports, state, `applications/queue.json`); never `profiles/` as a whole,
  `logs/`, `answers.json` or identity files. (d) authorization.yaml moves last, in its own PRs, so it stays out.
  The consequences say a data repo with no profile folder is unsupported.
- ADR-003 and ADR-007: the model scores, code acts. Nothing here gives the model a new action. Publishing and
  staging stay deterministic code.
- ADR-017 to ADR-022: submission, drafted answers, failure emails, public page fetching and the language rules
  are untouched. The failure-line change (item 4) must not drop the ADR-020 failure email.
- CLAUDE.md: the scan routine never pushes to `career-ai`; no personal data or credentials in a commit; the
  `applicant` and `answers` sections of `profile.yaml` are not read or printed; agents do not edit
  `authorization.yaml`, `config.yaml` or `profile.yaml`.
- `.github/workflows/decide.yml` is a protected path. Only a human edits it (docs/SDLC.md).
- Out of scope: item 7 (data repo `.gitignore` line `logs/apply/screens/`, a human data-repo change) and the
  `authorization.yaml` stage 2 PRs.
- Not in scope: the design of the replacement code. The spec decides it.

## Open questions

1. Precondition. The issue says not to start before the first scan routine run and one decide email link have
   worked on the moved layout, because the fallback is the rollback path until then. An agent cannot confirm
   this. Has the owner seen both work? Until the owner confirms, this intent should not move to build.
2. Decide workflow. `docs/decide-workflow.yml` is a template and the installed `.github/workflows/decide.yml` is
   protected and human-edited. Is the installed file already on the new staging path? Does the owner want only
   the template changed, with a note to compare the two?
3. Stale root folder. Should a leftover root `reports/`, `state/` or `applications/` be silently ignored, or
   should the run stop with a clear error? ADR-075 (d) chose refuse-to-run for a stale `authorization.yaml`.
   The spec decides, and should say whether the two cases match.
4. Faillog. Keep the "no profile folder at all" rule in `apply/faillog`, or drop it? It is unclear whether it
   still has a use once ADR-075's unsupported-layout consequence applies.
5. No profile folder. A data repo with no profile folder is unsupported (ADR-075 consequences). Should each code
   path raise a `ConfigError` as `layout.resolve` does (ADR-070), or may some keep a quiet default?
