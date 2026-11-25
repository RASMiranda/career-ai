# Intent: Move all owner-specific data in the data repo into profiles/<id>/ (phase C)

## Problem

After ADR-069 to ADR-072, the answer bank, apply log and standing files live under `profiles/<id>/` in `career-data`. Owner-specific data still sits at the data root: the application queue, reports, scan state, the authorization file and the `apply` section of `config.yaml`. A second user would need a second copy of each, or would share the owner's. Two stated rules also block the move. ADR-069 (d) keeps authorization, config, state and reports at the root "until the multi-user data model is decided", and ADR-071 (c) and ADR-072 keep the queue, run history and failure lines at the root until the owner decides whether the scan routine may commit under `profiles/`. The data README says the routine never pushes `profiles/`.

ADR-071 (c) and the data README also name files that do not exist (`logs/runs.jsonl`, `applications/answers.json`). Run history is `state/runs.jsonl`.

Reported by the owner (issue #118, RASMiranda).

## Proposed outcome

Outside `profiles/<id>/` the data repo holds no owner-specific data. The owner asked for these moves:

| From (data root) | To |
|---|---|
| `applications/queue.json` (the `profile` field stays as a key) | `profiles/<id>/applications/queue.json` |
| `reports/` | `profiles/<id>/reports/` |
| `state/` (seen-set, delivery journal, API budget, `state/runs.jsonl`, slug cache) | `profiles/<id>/state/` |
| `authorization.yaml` | `profiles/<id>/authorization.yaml` |
| `config.yaml`, `apply` section only | `profiles/<id>/apply/config.yaml` (name for the spec to settle) |

Budgets, sources, blacklist and `manual_channels` stay in the root `config.yaml`. The corrections to ADR-071 (c) and the data README are part of the outcome.

Done means all of these hold:
- The only tracked files outside `profiles/` are `README.md`, `.gitignore`, `.github/`, `tests/`, the slimmed `config.yaml` and `logs/apply/.gitkeep`.
- The scan routine publishes reports, state and queue under `profiles/<id>/`. It cannot touch `answer_bank.yaml`, `profile.yaml` or `authorization.yaml`.
- `python -m jobscan.applylog check --strict --data <path> --profile <id>` still prints ok with unchanged counts.
- New code reads no old root path (ADR-070, ADR-072).
- The full test suite and `tests/test_no_personal_data.py` pass.

## Affected users and systems

- The owner, who runs the scan routine and the browser-apply sessions, and who approves the data PR because it moves `authorization.yaml`.
- A future second user (the reason for the work). No second user is onboarded here.
- `career-ai` code: `src/jobscan/pipeline.py` (`PUBLISH_PATHS`, line 29), `layout.py`, `apply/faillog.py`, and every reader of the moved files. The issue counts about 12 source and 19 test references to `authorization.yaml`, 8 and 29 to `config.yaml`, and 12 and 29 to `state/`. The spec must list them all.
- `career-data`: the layout, its README and its `.gitignore`.
- The scan workflow, the routine prompt, the run prompts, the batch-job-apply skill and the project instructions, which name the old paths.

## Constraints

- **CLAUDE.md.** `career-ai` holds no personal data. The scan routine never pushes to `career-ai`. It never edits `authorization.yaml`, `config.yaml` or any `profile.yaml`, and never reads `applicant` or `answers`. It never runs `apply run`. Job text stays untrusted.
- **ADR-069 (d), ADR-071 (c), ADR-072.** The new ADR must supersede ADR-071 (c), ADR-069 (d) and the README rule "routine never pushes `profiles/`". ADR-072 says moving the queue and failure lines needs the owner's decision on whether the scan routine may commit under `profiles/`.
- **Publishing allowlist.** After the move, the routine publishes only `profiles/<id>/reports`, `profiles/<id>/state` and `profiles/<id>/applications`, never `profiles/` as a whole. A test must show that a commit touching any other profile file is refused.
- **ADR-063, ADR-069, ADR-071, ADR-072 order.** Three steps: a `career-ai` PR that reads the new paths with a LEGACY fallback, then a `career-data` PR that only renames, then a `career-ai` cleanup PR that removes the fallback. No browser-apply run or scan runs between the data PR and the cleanup unless the plan shows it is safe.
- **ADR-070, ADR-072.** The final code reads no old root path.
- **Security of the fallback.** A stale root `authorization.yaml` must never authorise anything. The fallback for this file is security-sensitive and needs its own treatment in the spec, for example no fallback, or a refusal when both copies exist.
- **Protected paths (ADR-024, ADR-025, `docs/SDLC.md`).** Agents cannot edit authorization, config, profiles, `docs/DECISIONS.md`, `.github/` or the routine prompt. The plan must mark human-only steps: the ADR, the workflow, the routine prompt, and the authorization and config moves.
- **Strict check.** The apply-log strict check must give unchanged counts (ADR-063, ADR-071 acceptance).
- **No personal data or credentials** in any commit or in these artifacts.

## Open questions

For the owner:
1. Is the scan routine allowed to commit under `profiles/<id>/` (reports, state, queue only)? Everything else depends on this (ADR-072).
2. `state/` mixes per-person files with platform-wide ones. Move it all, or split it? The issue lists seen-set, delivery journal, API budget, run history and slug cache. Which of these are per person is not decided.
3. Where do the sanitised failure lines of `apply/faillog.py` go (ADR-071 (c)): keep them in root `logs/apply/`, or write them under the profile of the failed run? Keeping them leaves one owner-specific path outside `profiles/`, against the stated goal.
4. What is the exact name and shape of the apply config file, and how does the fallback work for `authorization.yaml`?
5. Is it safe to run a scan or a browser-apply between the data PR and the cleanup PR? Without a fallback in the routine, it may not be.

Out of scope:
- Onboarding a second user.
- Changing budgets, sources, blacklist or `manual_channels`.
- Rate.xlsx and the CV PDFs (ADR-069 (e)).
- Any change to scoring, apply behaviour or the `apply run` authorization rules.
- Rewriting the history of `career-data`.
- The follow-up edits to run prompts, the skill and project instructions: tracked, but done by the owner after the data PR.
