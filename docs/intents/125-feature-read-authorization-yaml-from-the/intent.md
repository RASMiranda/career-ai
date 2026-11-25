# Intent: read authorization.yaml from the profile folder only, fail closed (#125)

## Problem

`authorization.yaml` is the owner's master switch: it says whether the scan may run and whether applications may be submitted (ADR-042). ADR-075 (d) moves it from the data repo root to `profiles/<id>/authorization.yaml`, but `load_authorization` in `src/jobscan/config.py` still reads `<root>/authorization.yaml`. While code can read either place, the owner cannot tell which file is in force, and a second profile would share the first one's switch.

This issue is the code half only. The data move in `career-data` is a separate PR that follows once this code is on `main`.

## Proposed outcome

Done, from the owner's side:

- Every command that loads authorization (`pipeline`, `validate`, `report`, `apply`) reads `profiles/<id>/authorization.yaml` and nothing else.
- With no profile copy, the command stops with a `ConfigError` that names the profile path and says the root copy is not read. It never falls back, even when a root copy exists.
- With several profiles and no `--profile`, the command stops with the same "pass --profile" error the other profile-scoped code gives.
- If `active` is not `true` in the profile file, `pipeline` still stops with "nothing was run" (unchanged).
- A test shows that no read of `root / "authorization.yaml"` remains in `src/jobscan`.
- Existing test fixtures that write a root `authorization.yaml` write the profile path instead, and the full suite passes.
- A missing or unreadable file never behaves as authorized. A routine that runs between the code merge and the data move stops and sends nothing.

## Affected users and systems

- The owner (`rui`): the scan routine stops until the data PR moves the file. This is intended and fails closed.
- Any later profile gets its own switch.
- Code: `config.load_authorization` and its callers in `pipeline.py`, `validate.py`, `report.py` and `apply/cli.py`. `bank.py` and `work_auth_standing` get their values through the `authorization` argument. That path stays, and only where the file comes from changes.
- Tests under `tests/` that write a root `authorization.yaml`.
- Out of scope:
  - Moving the real file in `career-data`.
  - Run prompts, skills and project-instruction wording.
  - Changing the contents or schema of `authorization.yaml`, including `application_submission`.
  - Moving any other file, or changing profile resolution generally.

## Constraints (ADRs and rules touched)

- ADR-075 (d): authorization moves last, with no fallback. Missing means inactive and the scan stops.
- ADR-070 and ADR-072: the precedent is profile path only, with no root fallback.
- ADR-042: this file gates submission. A silent fallback could switch submission on or off without the owner knowing.
- ADR-063: code ships before data.
- CLAUDE.md:
  - `authorization.yaml` is a protected path, and no agent edits it. Only the reading code changes.
  - The `applicant` and `answers` sections of a profile are never read, printed or copied.
  - No personal data goes in tests or fixtures (`test_no_personal_data.py`).
  - Tests must not be weakened.

## Open questions

1. **ADR conflict to resolve.** ADR-075 (d) says "a stale root copy makes the code refuse to run". The issue says the root copy is "not read" and only errors when the profile copy is missing. Which applies when both exist? The intent follows the issue (ignore the root copy). The spec should confirm this, or propose a superseding ADR if refusing is wanted.
2. How do callers get the profile? Reuse the existing profile resolver (`layout.resolve` style) or take a profile id.
3. Does every `apply` subcommand need `--profile` with several profiles, including `summary` and `enqueue`?
4. Should `validate` and `report` fail hard on a missing file, or report it as a problem and continue? Fail closed is the default.
5. Should the "active is not true" message name the profile path?
