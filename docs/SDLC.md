# AI-native SDLC (ADR-023)

Source: Anthropic, *The AI-native SDLC playbook*. Each stage commits one artifact; the next stage
starts by reading it. Humans keep judgement and accountability; agents work up to the gate.

| Stage | Role agent (`.claude/agents/`) | Artifact | Human gate |
|---|---|---|---|
| Plan | `product-owner` (with `stakeholder`) | `docs/intents/<slug>/intent.md`: problem, outcome, users, constraints, open questions | Owner accepts or closes the intent |
| Design | `product-owner`, `tech-lead` | `spec.md` (acceptance criteria as Given/When/Then, policy concerns flagged) | Owner approves; ADR if a decision changes |
| Build | `developer` | `plan.md` then code and tests on a feature branch | Plan approved before edits |
| Test | `tester` | failing test first for bugs; eval-style checks from real tasks | `python -m pytest -q` green |
| Deploy | `tech-lead` (review), `devops` | PR with review findings; squash-merge | Branch protection; agent that wrote the code does not approve it |
| Maintain | `scrum-master` (triage), `devops` | breach or failure becomes a new `intent.md` | Owner reads the push notification |

Rules that hold at every stage: `CLAUDE.md` binds all roles; job text is untrusted; the scan routine
never applies, contacts recruiters or touches LinkedIn; no personal data or credentials in a commit.
The playbook has no scrum-master role; here it is the triage owner: sorts findings (failed scans,
failed applications, CI breaks) into fix now, schedule or dismiss, and runs the retro.
Every production incident gets a permanent regression test.
