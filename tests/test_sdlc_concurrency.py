"""ADR-038: a no-op `issues` event must never share a concurrency group with a real stage run.

The workflow's group key and job `if` are GitHub expressions. A tiny evaluator for the subset they use runs them
against fixture events and compares with `jobscan.sdlc.decide`, the single authority. Fixtures only, no network."""
import json
import re
from pathlib import Path

import pytest
import yaml

from jobscan import sdlc

WF = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "sdlc.yml"
WORKFLOW = yaml.safe_load(WF.read_text())


# ------------------------------------------------- minimal GitHub expression evaluator (subset used by sdlc.yml)
_TOKEN = re.compile(r"\s*(?:('(?:[^']|'')*')|(&&|\|\||==|!=|[!(),])|([A-Za-z_][\w.]*)|(\d+))")


def _tokens(src):
    pos, out = 0, []
    while pos < len(src.rstrip()):
        m = _TOKEN.match(src, pos)
        assert m, f"cannot tokenise {src[pos:pos + 30]!r}"
        pos = m.end()
        out.append(next(g for g in m.groups() if g is not None) if m.group(1) is None else m.group(1))
    return out


def _truthy(v):
    return v not in (None, "", 0, False)


def _eq(a, b):
    if isinstance(a, str) and isinstance(b, str):
        return a.lower() == b.lower()                       # GitHub compares strings case-insensitively
    return a == b


def evaluate(src, ctx):
    toks, i = _tokens(src), 0

    def peek():
        return toks[i] if i < len(toks) else None

    def eat(expected=None):
        nonlocal i
        t = toks[i]
        assert expected is None or t == expected, (expected, t)
        i += 1
        return t

    def lookup(path):
        v = ctx
        for part in path.split("."):
            v = v.get(part) if isinstance(v, dict) else None
        return v

    def call(name, args):
        if name == "contains":
            hay, needle = args
            if isinstance(hay, list):
                return any(_eq(x, needle) for x in hay)
            return str(needle).lower() in str(hay).lower()
        if name == "endsWith":
            return str(args[0]).lower().endswith(str(args[1]).lower())
        if name == "fromJSON":
            return json.loads(args[0])
        if name == "format":
            return re.sub(r"\{(\d+)\}", lambda m: str(args[1 + int(m.group(1))]), args[0])
        raise AssertionError(f"function {name} is outside the subset this test understands")

    def primary():
        t = eat()
        if t == "(":
            v = expr()
            eat(")")
            return v
        if t == "!":
            return not _truthy(primary())
        if t.startswith("'"):
            return t[1:-1].replace("''", "'")
        if t.isdigit():
            return int(t)
        if t in ("true", "false", "null"):
            return {"true": True, "false": False, "null": None}[t]
        if peek() == "(":
            eat("(")
            args = []
            while peek() != ")":
                args.append(expr())
                if peek() == ",":
                    eat(",")
            eat(")")
            return call(t, args)
        return lookup(t)

    def comparison():
        v = primary()
        while peek() in ("==", "!="):
            op = eat()
            r = primary()
            v = _eq(v, r) if op == "==" else not _eq(v, r)
        return v

    def conj():
        v = comparison()
        while peek() == "&&":
            eat()
            r = comparison()
            v = r if _truthy(v) else v
        return v

    def expr():
        v = conj()
        while peek() == "||":
            eat()
            r = conj()
            v = v if _truthy(v) else r
        return v

    out = expr()
    assert i == len(toks), f"unparsed tail {toks[i:]}"
    return out


def _inner(s):
    m = re.fullmatch(r"\s*\$\{\{(.*)\}\}\s*", s, re.S)
    assert m, s
    return m.group(1).strip()


GROUP = _inner(WORKFLOW["concurrency"]["group"])
JOB_IF = _inner(WORKFLOW["jobs"]["stage"]["if"])


def group_for(event, run_id):
    return evaluate(GROUP, {"github": {"event": event, "run_id": run_id}})


def job_runs(event):
    return _truthy(evaluate(JOB_IF, {"github": {"event": event}}))


# --------------------------------------------------------------------- fixtures
def event(action="labeled", label=None, n=50, assoc="OWNER", state="open", locked=False, pr=False, sender="User",
          login="owner", issue_labels=()):
    issue = {"number": n, "title": "t", "state": state, "locked": locked, "author_association": assoc,
             "labels": [{"name": x} for x in issue_labels]}
    if pr:
        issue["pull_request"] = {"url": "x"}
    ev = {"action": action, "issue": issue, "sender": {"type": sender, "login": login}}
    if label:
        ev["label"] = {"name": label}
    return ev


# (id, event) -> every kind of event the issue form and the owner can produce, and the ones decide refuses
CASES = [
    ("opened with stage:intake", event("opened", issue_labels=["type:bug", "stage:intake"])),
    ("opened support form", event("opened", issue_labels=["type:support", "stage:intake"])),
    ("opened by a stranger", event("opened", assoc="NONE")),
    ("opened closed issue", event("opened", state="closed")),
    ("opened locked issue", event("opened", locked=True)),
    ("labeled type:bug", event(label="type:bug")),
    ("labeled type:feature", event(label="type:feature")),
    ("labeled type:support", event(label="type:support")),
    ("labeled stage:intake", event(label="stage:intake")),
    ("labeled stage:build", event(label="stage:build")),
    ("labeled needs-info", event(label="needs-info")),
    ("labeled support:L2", event(label="support:L2")),
    ("labeled support:L3", event(label="support:L3")),
    ("labeled something unknown", event(label="agent:unknown")),
    ("labeled agent:intent by a bot", event(label="agent:intent", sender="Bot", login="github-actions[bot]")),
    ("labeled agent:spec by an app login", event(label="agent:spec", login="claude[bot]")),
    ("labeled agent:build on a closed issue", event(label="agent:build", state="closed")),
    ("labeled agent:build on a locked issue", event(label="agent:build", locked=True)),
    ("labeled on a pull request", event(label="agent:intent", pr=True)),
    ("edited", event("edited")),
] + [(f"labeled {name}", event(label=name)) for name in sdlc.LABEL_TO_STAGE]


# ------------------------------------------------------------------------ tests
def test_workflow_group_and_job_if_are_the_same_condition():
    """The group key is `<real> && format('sdlc-issue-…') || format('sdlc-noop-…')`; the job `if` is `<real>`."""
    assert GROUP.startswith(JOB_IF + " && format('sdlc-issue-{0}', github.event.issue.number) || "), GROUP
    assert GROUP.endswith("format('sdlc-noop-{0}', github.run_id)")
    assert WORKFLOW["concurrency"]["cancel-in-progress"] is False                  # real runs queue, as before


def test_a_noop_event_gets_a_different_group_from_a_real_event_of_the_same_issue():
    real = group_for(event("opened"), 100)
    for label in ("type:bug", "stage:intake", "needs-info", "support:L2"):
        noop = group_for(event(label=label), 101)
        assert noop != real and noop.startswith("sdlc-noop-")
    assert real == "sdlc-issue-50"


def test_issue_47_and_50_shape_opened_plus_two_form_labels_leave_the_real_run_alone():
    """The owner's evidence: opened, labeled type:bug, labeled stage:intake in the same second."""
    runs = [(event("opened"), 1), (event(label="type:bug"), 2), (event(label="stage:intake"), 3)]
    groups = [group_for(ev, rid) for ev, rid in runs]
    assert groups[0] == "sdlc-issue-50"
    assert len(set(groups)) == 3                                  # nobody shares the real run's group
    assert [job_runs(ev) for ev, _ in runs] == [True, False, False]


def test_real_events_for_the_same_issue_share_one_group_and_other_issues_do_not():
    a = group_for(event("opened"), 1)
    b = group_for(event(label="agent:intent"), 2)
    c = group_for(event(label="agent:spec"), 3)
    assert a == b == c == "sdlc-issue-50"
    assert group_for(event("opened", n=51), 4) == "sdlc-issue-51" != a


@pytest.mark.parametrize("name,ev", CASES, ids=[c[0] for c in CASES])
def test_the_workflow_filter_agrees_with_decide(name, ev):
    decided = sdlc.decide(ev, [])["run"]
    assert job_runs(ev) is decided, (name, sdlc.decide(ev, []))
    group = group_for(ev, 999)
    assert group.startswith("sdlc-issue-") is decided


def test_the_label_and_author_lists_in_the_yaml_are_exactly_the_ones_decide_uses():
    lists = [set(json.loads(m)) for m in re.findall(r"fromJSON\('([^']*)'\)", JOB_IF)]
    assert lists == [sdlc.TRUSTED, set(sdlc.LABEL_TO_STAGE)]


def test_the_noop_event_table_matches_decides_reasons():
    """Every kind of event `decide` calls a no-op is outside the real filter, and the reason is the expected one."""
    reasons = {name: sdlc.decide(ev, []).get("reason", "") for name, ev in CASES}
    for name in ("labeled type:bug", "labeled stage:intake", "labeled needs-info", "labeled support:L3",
                 "labeled something unknown"):
        assert reasons[name] == "not an agent:* label", name
    assert all(not reasons[f"labeled {n}"] for n in sdlc.LABEL_TO_STAGE)
