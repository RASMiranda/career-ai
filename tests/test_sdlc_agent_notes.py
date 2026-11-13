"""The agent notes (ADR-055): denied tool names and the stage agent's last message, read from the action's execution file.

The shape of the execution file is ASSUMED, not verified against the action's source (the pinned action could not be
read from here): a JSON array of messages whose last ``type: result`` message carries ``permission_denials`` (a list of
{tool_name, tool_use_id, tool_input}) and ``result`` (text). The parser also takes one object or one object per line.
"""

import json

import pytest

from jobscan import sdlc

FAKE_TOKEN = "sk-ant-oat01-" + "FAKE" * 8                 # obviously fake; shaped like an OAuth token
SECRET_INPUT = "echo " + FAKE_TOKEN + " > /tmp/x"


def denial(name, tool_input=None):
    return {"tool_name": name, "tool_use_id": "toolu_01", "tool_input": tool_input or {"command": SECRET_INPUT}}


def result_file(tmp_path, name, *, denials=(), result="Built the thing.", extra=None):
    message = {"type": "result", "subtype": "success", "result": result, "permission_denials": list(denials)}
    message.update(extra or {})
    path = tmp_path / name
    path.write_text(json.dumps([{"type": "assistant", "message": {"content": "work"}}, message]))
    return str(path)


# ----------------------------------------------------------------- the parser
def test_denial_counts_and_tool_names_are_read_and_the_tool_input_never_is(tmp_path):
    stage = result_file(tmp_path, "stage.json", denials=[denial("Bash"), denial("Write")])
    review = result_file(tmp_path, "review.json", denials=[denial("Write"), denial("Read"), denial("Write")])
    notes = sdlc.agent_notes(stage, review)
    assert notes["stage"] == {"count": 2, "tools": ["Bash", "Write"]}
    assert notes["review"] == {"count": 3, "tools": ["Write", "Read"]}
    text = json.dumps(notes) + sdlc.denial_line(notes)
    assert FAKE_TOKEN not in text and "tool_input" not in text and "/tmp/x" not in text and "echo" not in text


def test_the_denial_line_has_the_fixed_format_and_says_none_when_there_are_no_denials(tmp_path):
    stage = result_file(tmp_path, "stage.json", denials=[denial("Bash")])
    review = result_file(tmp_path, "review.json", denials=[denial("Write"), denial("Read"), denial("Write")])
    assert sdlc.denial_line(sdlc.agent_notes(stage, review)) == \
        "Permission denials: stage agent 1 (Bash); reviewers 3 (Write, Read)"
    assert sdlc.denial_line(sdlc.agent_notes(result_file(tmp_path, "s.json"), None)) == "Permission denials: none"
    only_review = sdlc.agent_notes(None, review)
    assert sdlc.denial_line(only_review) == "Permission denials: stage agent 0; reviewers 3 (Write, Read)"


@pytest.mark.parametrize("path", [None, "", "missing.json"])
def test_a_missing_file_gives_a_neutral_result(tmp_path, path):
    notes = sdlc.agent_notes(str(tmp_path / path) if path else path, None)
    assert notes == {"stage": {"count": 0, "tools": []}, "review": {"count": 0, "tools": []}, "last_message": ""}
    assert sdlc.denial_line(notes) == "Permission denials: none"


@pytest.mark.parametrize("garbage", ["not json at all", "{\"type\": ", "", "[1, 2, \"x\"]", "null", "\x00\xff"])
def test_garbage_gives_a_neutral_result_and_never_raises(tmp_path, garbage):
    path = tmp_path / "exec.json"
    path.write_bytes(garbage.encode("utf-8", errors="surrogatepass") if garbage else b"")
    notes = sdlc.agent_notes(str(path), str(path))
    assert notes["stage"]["count"] == 0 and notes["review"]["count"] == 0 and notes["last_message"] == ""


def test_a_file_with_no_result_message_or_no_denials_list_is_neutral(tmp_path):
    no_result = tmp_path / "a.json"
    no_result.write_text(json.dumps([{"type": "assistant", "message": {"content": "hi"}}]))
    no_list = tmp_path / "b.json"
    no_list.write_text(json.dumps([{"type": "result", "result": "done", "permission_denials": "Bash"}]))
    assert sdlc.agent_notes(str(no_result), None)["stage"] == {"count": 0, "tools": []}
    notes = sdlc.agent_notes(str(no_list), None)
    assert notes["stage"] == {"count": 0, "tools": []} and notes["last_message"] == "done"


def test_the_last_result_message_wins_and_one_object_or_one_object_per_line_are_accepted(tmp_path):
    first = {"type": "result", "result": "old", "permission_denials": [denial("Bash")]}
    last = {"type": "result", "result": "new", "permission_denials": []}
    as_array = tmp_path / "array.json"
    as_array.write_text(json.dumps([first, last]))
    assert sdlc.agent_notes(str(as_array), None)["last_message"] == "new"
    one = tmp_path / "one.json"
    one.write_text(json.dumps(first))
    assert sdlc.agent_notes(str(one), None)["stage"]["tools"] == ["Bash"]
    per_line = tmp_path / "lines.json"
    per_line.write_text("\n".join([json.dumps({"type": "assistant"}), "not json", json.dumps(first)]))
    assert sdlc.agent_notes(str(per_line), None)["stage"]["count"] == 1


def test_tool_names_are_sanitized_to_a_safe_set_and_cut_at_forty_characters(tmp_path):
    hostile = "Write\n## @evil `x` , y"
    stage = result_file(tmp_path, "stage.json", denials=[denial(hostile), denial("A" * 60), denial("Bash(git diff:*)"),
                                                          {"tool_name": 7}, "not an object"])
    tools = sdlc.agent_notes(stage, None)["stage"]["tools"]
    assert tools == ["Writeevilxy", "A" * 40, "Bash(gitdiff:*)", "(unnamed)"]
    assert all(set(t) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_:().*-") for t in tools)
    assert sdlc.agent_notes(stage, None)["stage"]["count"] == 5                  # every entry counts, named or not


def test_the_last_message_is_the_result_text_trimmed_to_fifteen_hundred_characters(tmp_path):
    stage = result_file(tmp_path, "stage.json", result="  " + "x" * 3000)
    message = sdlc.agent_notes(stage, None)["last_message"]
    assert len(message) == 1500 and message == "x" * 1500


# ------------------------------------------------ what the post step may write
def test_a_fake_token_in_the_last_message_is_withheld_and_nothing_is_fenced(tmp_path):
    stage = result_file(tmp_path, "stage.json", result=f"I used {FAKE_TOKEN} to test")
    out = sdlc.agent_note_outputs(sdlc.agent_notes(stage, None), no_report=True)
    assert FAKE_TOKEN not in out["message"] and "withheld by the safety check" in out["message"]
    assert "I used" not in out["message"]


def test_the_last_message_is_shown_under_its_untrusted_heading_only_when_there_was_no_report(tmp_path):
    stage = result_file(tmp_path, "stage.json", result="Partly done; the tests are not run.")
    notes = sdlc.agent_notes(stage, None)
    with_report = sdlc.agent_note_outputs(notes, no_report=False)
    assert with_report["message"] == ""
    without = sdlc.agent_note_outputs(notes, no_report=True)
    assert "**Agent's last message (untrusted, not reviewed)**" in without["message"]
    assert "```text\nPartly done; the tests are not run.\n```" in without["message"]


def test_a_message_with_code_fences_gets_a_longer_fence_so_it_cannot_break_out(tmp_path):
    stage = result_file(tmp_path, "stage.json", result="before\n```\nafter")
    block = sdlc.agent_note_outputs(sdlc.agent_notes(stage, None), no_report=True)["message"]
    assert "````text\nbefore\n```\nafter\n````" in block


def test_a_token_in_a_denied_tool_name_is_withheld_from_the_summary_and_the_comment(tmp_path):
    fake_name = "ghp_" + "A" * 36                                             # matches the credential pattern
    stage = result_file(tmp_path, "stage.json", denials=[denial(fake_name)])
    out = sdlc.agent_note_outputs(sdlc.agent_notes(stage, None), no_report=False)
    assert fake_name not in out["summary"] and fake_name not in out["denials"]
    assert "withheld by the safety check" in out["summary"] and out["denials"].count("withheld") == 1


def test_the_summary_is_always_written_and_the_comment_line_only_when_a_denial_happened(tmp_path):
    quiet = sdlc.agent_note_outputs(sdlc.agent_notes(result_file(tmp_path, "q.json"), None), no_report=False)
    assert quiet["summary"] == "Permission denials: none\n" and quiet["denials"] == ""
    loud = sdlc.agent_note_outputs(sdlc.agent_notes(result_file(tmp_path, "l.json", denials=[denial("Bash")]), None),
                                   no_report=False)
    assert loud["summary"] == "Permission denials: stage agent 1 (Bash); reviewers 0\n"
    assert loud["denials"] == loud["summary"]


def test_the_cli_writes_the_three_outputs_from_the_files(tmp_path):
    import os
    import subprocess
    import sys

    stage = result_file(tmp_path, "stage.json", denials=[denial("Bash")], result="last")
    outs = {k: str(tmp_path / f"{k}.txt") for k in ("summary", "denials", "message")}
    env = {**os.environ, "PYTHONPATH": str(sdlc.__file__).rsplit("/jobscan/", 1)[0]}
    run = subprocess.run([sys.executable, "-P", "-m", "jobscan.sdlc", "agent-notes", "--stage", stage,
                          "--no-report", "--summary-out", outs["summary"], "--denials-out", outs["denials"],
                          "--message-out", outs["message"]], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert run.returncode == 0, run.stderr
    assert (tmp_path / "summary.txt").read_text() == "Permission denials: stage agent 1 (Bash); reviewers 0\n"
    assert "last" in (tmp_path / "message.txt").read_text() and FAKE_TOKEN not in (tmp_path / "denials.txt").read_text()
