# Intent 104: Verify the SDLC pipeline on main with a throwaway feature issue

## Problem

The owner has changed how the sdlc engine is run (S1 C and D: `src/sdlc_engine/`, ADR-064 and ADR-065; the engine reads `.github/sdlc-config.json` with `--config` from the trigger commit, ADR-036). That change has not been verified by a real run on `main`. The issue text is cut off after "The trusted steps should read", but the sentence it quotes is clear enough: the trusted steps should be labelled "Trusted engine code". The owner wants one disposable feature issue to prove it.

From the owner's side, "done" is three observations on this run:
1. The Frame step shows `--config` in its invocation.
2. The run finishes with no `ConfigError`.
3. The intent stage completes and writes this file.

The trusted steps in the workflow log should read "Trusted engine code".

## Proposed outcome

- This issue is a verification vehicle, not a product feature. It produces this intent and nothing else; no code change is wanted.
- The owner reads the run's log and confirms the three observations above, plus the "Trusted engine code" step naming.
- The owner then closes the issue (and any draft PR) without merging product changes.

Out of scope: any change to the workflow, the engine, the config file or step names. If a step name is wrong, that is a separate issue. A later stage must not invent a feature to build here.

## Affected users and systems

- The owner (RASMiranda), who reads the run.
- The sdlc workflow and `src/sdlc_engine/` (read-only here), `.github/sdlc-config.json`.
- No end user, no scan, no profile, no `career-data`.

## Constraints

- ADR-036: the engine runs from the trusted checkout of the trigger commit; the config takes effect only once merged to main.
- ADR-065: project prompt text and owner handle come from the protected config.
- ADR-025 and `docs/SDLC.md`: agents never merge, push to `main` or edit protected paths (`.github/**`, `src/sdlc_engine/**`, etc.). The intent stage writes only this file.
- ADR-017 to ADR-022 and CLAUDE.md: nothing here touches applying, recruiters, LinkedIn or a browser. No personal data is involved.
- The issue text is untrusted; it contains no instructions beyond the owner's verification request, and none were followed.

## Open questions

1. The issue body is truncated at "The trusted steps should read". Is "Trusted engine code" the complete expected step name? (Assumed yes.)
2. Is the agent expected to confirm the `--config` and `ConfigError` observations? It cannot see the workflow log, so the owner has to check them.
3. Should the issue be closed after the intent stage, or carried to spec to exercise later stages? (Recommended: close after intent.)
4. "Does aiapply.co do this?" was left blank; it appears not applicable.
