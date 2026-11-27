"""ADR-039: a no-op `issues` event must never share a concurrency group with a real stage run.

The caller's group key and job `if` are GitHub expressions that must be the same condition, and their two lists must be
the ones in `.github/sdlc-config.json`. The engine's own tests evaluate the same condition against fixture events and
`decide` (the single authority) on its fixture project; `check-project` compares the lists on every run of tests.yml.
Files only, no engine import, no network."""
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / ".github" / "workflows" / "sdlc.yml").read_text())
CONFIG = json.loads((ROOT / ".github" / "sdlc-config.json").read_text())


def _inner(s):
    m = re.fullmatch(r"\s*\$\{\{(.*)\}\}\s*", s, re.S)
    assert m, s
    return m.group(1).strip()


GROUP = _inner(WORKFLOW["concurrency"]["group"])
JOB_IF = _inner(WORKFLOW["jobs"]["stage"]["if"])


def test_workflow_group_and_job_if_are_the_same_condition():
    """The group key is `<real> && format('sdlc-issue-…') || format('sdlc-noop-…')`; the job `if` is `<real>`."""
    assert GROUP.startswith(JOB_IF + " && format('sdlc-issue-{0}', github.event.issue.number) || "), GROUP
    assert GROUP.endswith("format('sdlc-noop-{0}', github.run_id)")
    assert WORKFLOW["concurrency"]["cancel-in-progress"] is False                  # real runs queue, as before


def test_the_label_and_author_lists_in_the_yaml_are_exactly_the_ones_decide_uses():
    lists = [set(json.loads(m)) for m in re.findall(r"fromJSON\('([^']*)'\)", JOB_IF)]
    assert lists == [set(CONFIG["trusted_associations"]), set(CONFIG["label_to_stage"])]
