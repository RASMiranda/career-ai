# Intent 100: Verify the sdlc_engine rename on main with a throwaway feature issue

## Problem
ADR-064 (#99) moved the sdlc engine from `jobscan.sdlc` to the top-level package `sdlc_engine`. Unit tests pass, but only a real workflow run on `main` shows that the workflow, which runs from main's file and from a trusted copy of the repo, uses the new package. The owner wants that confirmed the way it was confirmed before: by running one throwaway feature issue (this one) through the pipeline.

## Proposed outcome
Done means the step logs of this run show:
- Decide, Budget, Skip, Frame and Post each invoke `sdlc_engine`.
- The trusted copy shows `trusted/src/sdlc_engine/__init__.py`.
- No `ConfigError` appears anywhere in the logs.
- No `jobscan.sdlc` appears anywhere in the logs.

This issue produces no product change. After the check, the owner closes it.

## Affected users and systems
- The owner, who reads the logs and closes the issue.
- The sdlc workflow (`.github/workflows/sdlc.yml`), `.github/sdlc-config.json` and `src/sdlc_engine/`, read-only for this purpose.
- No scan, profile, career-data or apply path is involved.

## Constraints
- ADR-064: the engine is `sdlc_engine`; the only `jobscan` mention left is one prompt string, described in that ADR's Consequences. A match on that string is not `jobscan.sdlc`.
- ADR-060: the engine's config file is read by the workflow from main. A `ConfigError` would mean a malformed or mismatched file.
- ADR-025 and docs/SDLC.md: agents never merge, push to main or change protected paths. This stage writes only this file.
- No personal data, credentials or `career-data` are touched.

## Out of scope
- Any code, config or workflow change.
- Fixing anything the check turns up. A failure becomes its own bug issue.
- Verifying stages after intent (spec, build, review) beyond what the logs already show.

## Open questions
- Which stages count? The issue names Decide, Budget, Skip, Frame and Post. Is every other step, such as the trusted-copy checkout, expected to show only `sdlc_engine` too?
- Should the check cover the whole pipeline to merge, or only the stages run by this issue's labels?
- Who reads the logs? A human must, because agents have no network.
