# Spec: Move all owner-specific data in the data repo under profiles/<id>/ (phase C)

Issue #118. Owner decisions (issue comments) are settled and recorded here. `<id>` is the profile id; `<data>` the data repo.

## Delivery in two stages (owner decision C4)

- **Stage 1** (queue, reports, state, apply config, apply-run files, failure lines): career-ai PR with `LEGACY` fallback, then a rename-only career-data PR, then a career-ai cleanup PR removing the fallback (ADR-063, ADR-069, ADR-071, ADR-072).
- **Stage 2** (`authorization.yaml` only): after the cleanup PR, one small career-ai PR plus a matching data PR. No fallback, fails closed.

## Requirements

Moves (same relative name inside the profile folder):

1. `applications/queue.json` -> `profiles/<id>/applications/queue.json`; the `profile` field stays a key. (`apply/queue.py:28`)
2. `applications/answers.json` -> `profiles/<id>/applications/answers.json`. (`apply/answers.py:88`)
3. `logs/runs.jsonl` -> `profiles/<id>/logs/runs.jsonl`. (`apply/runlog.py:15`)
4. `reports/<day>.md` -> `profiles/<id>/reports/`. (`report.py:196-203`) The apply summary `reports/applications.md` (`apply/cli.py:312`) goes there too.
5. All of `state/` -> `profiles/<id>/state/`: `job-scan-seen.json`, `-budget.json`, `-delivery.json` (`state.py:30,51,80`), `runs.jsonl`, `slug_cache.json` (`apply/slug_cache.py:19`), `linkedin-cooldown.json` (`apply/linkedin.py:27`); `collect.py:43` creates the folder. Seen-set and API budget become per profile.
6. Failure lines of `apply/faillog.py` go to `profiles/<id>/logs/apply/`, the profile taken from the queue row of the failed job. No root exception.
7. The `apply` section of root `config.yaml` -> `profiles/<id>/apply/config.yaml`. `budgets`, `sources`, `blacklist`, `manual_channels` stay in root `config.yaml`. Reader: `config.py:58-69`.
8. `authorization.yaml` -> `profiles/<id>/authorization.yaml` (stage 2 only). Readers: `config.py:69`, `pipeline.py:78-83`, `validate.py:86`, `report.py`, `apply/authz.py`, `apply/policy.py`, `bank.py`, `apply/cli.py:173` (messages).

Paths and fallback:

9. All paths come from `layout.resolve(root, pid, rel)`; `layout.py` docstring and `apply_path` lose the "stay at the root" text. No module builds a moved path by hand.
10. Stage 1 `LEGACY`: while a profile folder lacks the new file and the root one exists, read the root file, tagged `LEGACY`, with one warning. Removed in the cleanup PR. After it, a root copy is never read or written (ADR-070, ADR-072).
11. `authorization.yaml` has no fallback ever. Missing `profiles/<id>/authorization.yaml` = inactive: the scan stops ("nothing was run") and auto-apply is off. If a root `authorization.yaml` exists, the code refuses to run with an error naming the file and never reads it.
12. A data repo with no profile folder is no longer supported for the moved files (accepted, as ADR-070).

Publishing (owner decision 1):

13. `pipeline.PUBLISH_PATHS` becomes a per-profile allowlist built from the profile ids: `profiles/<id>/reports`, `profiles/<id>/state`, `profiles/<id>/applications/queue.json` (the single file, see R15). Never `profiles/` as a whole, never `profiles/<id>/logs`. Only these are passed to `git add`.
14. Before commit, `pipeline` checks the staged paths (`git diff --cached --name-only`). Any path outside the allowlist, including `answer_bank.yaml`, `profile.yaml`, `authorization.yaml`, `apply/`, `cv_manifest.json`, `logs/`, fails the run with nothing committed or pushed. The check is code, not prompt text.
15. `applications/answers.json` is under the allowlisted `applications/`; the routine never writes it, owner sessions do. Requirement 14 would not refuse a routine commit that includes it, so the allowlist entry is the single file `profiles/<id>/applications/queue.json`, never the folder. The owner has settled that `answers.json` stays out of the routine's reach.

Docs and checks:

16. `applylog check --strict --data <path> --profile <id>` prints `ok` with unchanged row, legacy and warning counts.
17. Correct ADR-071 (c) and the data README: `applications/answers.json` and `logs/runs.jsonl` are created on first use of `apply questions` / `apply run`; scan run history is `state/runs.jsonl`. Names are not deleted.
18. New ADR supersedes ADR-069 (d), ADR-071 (c), the "stay at the root" line in ADR-072 and the README rule "routine never pushes `profiles/`". Records the allowlist and the stage-2 no-fallback rule.
19. Tests that build a data repo gain a profile folder. `tests/test_no_personal_data.py` and the full suite pass.

## Acceptance criteria

- **A1** Given a data repo after stage 1, when tracked files outside `profiles/` are listed, then they are `README.md`, `.gitignore`, `.github/`, `tests/`, root `config.yaml` (slimmed), `authorization.yaml` (until stage 2) and `logs/apply/.gitkeep`. After stage 2 the file `authorization.yaml` is gone from that list.
- **A2** Given a scan run, when it publishes, then reports, state and queue land under `profiles/<id>/` and the root has no new `reports/`, `state/` or `applications/`.
- **A3** Given two profiles, when each scans, then each has its own seen-set, budget and delivery journal, and publishes only its own folders.
- **A4** Given a staged change to `answer_bank.yaml`, `profile.yaml`, `authorization.yaml`, `apply/config.yaml`, `logs/runs.jsonl` or `applications/answers.json`, when `pipeline` publishes, then it exits non-zero and nothing is committed.
- **A5** Given `PUBLISH_PATHS`, then no entry is `profiles` or `profiles/<id>`.
- **A6** Given stage 1 code and a checkout before the move, when it runs, then it reads the root files with a `LEGACY` warning; given the cleanup code, then it does not read them.
- **A7** Given a failed apply job whose queue row names a profile, when `FailureLog` writes, then the line is in `profiles/<id>/logs/apply/` and `apply failures` reads it from there.
- **A8** Given `apply` settings in `profiles/<id>/apply/config.yaml`, when the apply run loads config, then it uses them; the same keys in root `config.yaml` are ignored after cleanup.
- **A9** (stage 2) Given no `profiles/<id>/authorization.yaml`, then `pipeline prepare` stops with "nothing was run" and `apply run --mode auto` refuses.
- **A10** (stage 2) Given a root `authorization.yaml` with `active: true` and none under the profile, then the code refuses to run, names the stale file, and does not read its content.
- **A11** Given the moved layout, then `applylog check --strict` prints `ok` with unchanged counts.
- **A12** Given the final code, then a grep of `src/` finds no root-path construction of a moved file outside tests that assert refusal.
- **A13** Given the suite, then `python -m pytest -q` and `tests/test_no_personal_data.py` pass.

## Non-goals

Second-user onboarding; changes to budgets, sources, blacklist, `manual_channels`; Rate.xlsx and CV PDFs (ADR-069 (e)); scoring or apply behaviour; rewriting career-data history; follow-up edits to run prompts, the `batch-job-apply` skill and project instructions (owner, after the data PR).

## Concerns flagged

- **C1** (ADR-069 (d), ADR-071 (c), ADR-072, README) Needs the new ADR. `docs/DECISIONS.md` is protected: human-only.
- **C2** (ADR-024, ADR-025, CLAUDE.md "routine never edits authorization/profile") The routine gains write access inside `profiles/`. Only the allowlist and the staged-path check protect the answer bank, profile and authorization. R13-R15, A4, A5 need close review.- **C3** Failure lines are written by owner sessions, so `logs/apply` stays out of the allowlist. Needs `FailureLog` to receive the profile; if a failure has no queue row, the line is skipped with a warning, never written to the root (R6).
- **C4** (ADR-042) With no fallback, `authorization.yaml` moves last. The scan routine is paused for stage 2 only. Moving it earlier breaks the routine the moment the code merges.
- **C5** Per-profile state: each profile gets its own API budget and dedup. Accepted by owner for one user.
- **C6** Data repos without a profile folder lose support for moved files (ADR-070 precedent). Many tests change.
- **C7** (ADR-024, ADR-025) Human-only: ADR, `.github/workflows` (including `decide.yml`), routine prompt and trigger, `authorization.yaml` and `config.yaml` moves, and the career-data PRs.
- **C8** (ADR-063) Cutover: scan routine paused while the data PR is open and until the cleanup PR; no browser-apply run between data PR and cleanup. Stage 2 repeats the pause.
- **C9** `career-data/.github/workflows/decide.yml` runs `jobscan.decide --data .` and commits `applications/queue.json`. It must pass the profile and commit `profiles/<id>/applications/queue.json`. Human-only, inside the data PR. `decide` must accept `--profile`. If `decide` runs between the PRs it conflicts: keep it paused too.
- **C10** `apply/cli.py` summary report and `kit.py` may also hold paths in `reports/` or `applications/`. The plan lists every reference by grep, not by this spec's list, which is a start.
- **C11** The issue text called `answers.json` and `logs/runs.jsonl` nonexistent; the owner ruled they are created on first use. Only wording is corrected (R17).

## Test plan

New or changed tests (the failing test first):

- `test_layout.py`: new names resolve under the profile; no root fallback after cleanup; `LEGACY` path warns in stage 1.
- `test_pipeline.py`: allowlist has no `profiles` entry (A5); staged forbidden file refuses and nothing is committed (A4); a git fixture with real `git init` stages each forbidden name; publish commits only allowed paths (A2); two profiles (A3).
- `test_profiles.py` / `test_doctor.py`: stage-2 missing and stale root authorization (A9, A10), content of the stale file never read (assert by an unreadable file or a spy).
- `test_apply_core.py`, `test_answers.py`, `test_store.py`: queue, answers, run log, slug cache, cooldown, failure lines under the profile (A7).
- `test_linkedin_easy_apply.py`: cooldown path.
- `test_blacklist*.py`, `test_guard.py`, `test_kit.py`, `test_clip.py`: build a profile folder in fixtures.
- Apply config: `profiles/<id>/apply/config.yaml` read; root `apply` ignored after cleanup (A8).
- `applylog check --strict` counts fixture (A11).
- `test_sdlc*.py`, `tests/golden/prompt-*.md`: update only where they name moved paths, never weaken a guard.
- Full run: `python -m pytest -q`, including `tests/test_no_personal_data.py`.
