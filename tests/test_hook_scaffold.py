"""Tests for hook_scaffold.py. Specs are written into tmp_path; generated hooks run against a small stand-in for
the cc-hooks library, so these tests do not need cc-hooks installed."""

from __future__ import annotations

import io
import json
import runpy
import sys
import textwrap
from contextlib import redirect_stdout

import pytest
from conftest import load_script, run_json, run_main, write_files

mod = load_script("hook-author", "hook_scaffold.py")
SPEC = """
name: deny-env-read
event: PreToolUse
matcher: Bash
action: block
pattern: (^|\\s)cat\\s+\\S*\\.env\\b
message: Reading .env prints secrets into the transcript.
match_example: cat .env
nomatch_example: ls -la
"""
FAKE_CC_HOOKS = """
import json, sys

class HookInputError(Exception):
    pass

class Event:
    def __init__(self, data):
        self.__dict__.update(data)
        ti = data.get("tool_input") or {}
        self.command = ti.get("command")
        self.file_path = ti.get("file_path")

class PreToolUse(Event): pass
class PostToolUse(Event): pass
class UserPromptSubmit(Event): pass
class Stop(Event): pass
class SessionStart(Event): pass

def read_event(strict=True):
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except ValueError:
        raise HookInputError("bad")
    return {c.__name__: c for c in Event.__subclasses__()}[data["hook_event_name"]](data)

class Decision:
    def __init__(self, payload):
        self.payload = payload
    def exit(self):
        if self.payload is not None:
            print(json.dumps(self.payload))
        sys.exit(0)

def deny(reason, event="PreToolUse"):
    return Decision({"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": reason}})
def allow(reason=None, event="PreToolUse"):
    return Decision({"hookSpecificOutput": {"permissionDecision": "allow"}})
def block(reason, event="Stop"):
    return Decision({"decision": "block", "reason": reason})
def add_context(text, event="PostToolUse"):
    return Decision({"hookSpecificOutput": {"additionalContext": text}})
def update_input(new, decision="allow", reason=None, event="PreToolUse"):
    return Decision({"hookSpecificOutput": {"permissionDecision": decision, "updatedInput": new}})
def no_decision():
    return Decision(None)
"""


def spec(tmp_path, text: str = SPEC, name: str = "spec.txt") -> str:
    write_files(tmp_path, {name: text})
    return str(tmp_path / name)


def run_hook(hook_path, payload, monkeypatch) -> str:
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload if isinstance(payload, str) else json.dumps(payload)))
    out = io.StringIO()
    with redirect_stdout(out):
        with pytest.raises(SystemExit):
            runpy.run_path(str(hook_path), run_name="__main__")
    return out.getvalue()


@pytest.fixture
def fake_cc_hooks(tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "cc_hooks.py").write_text(textwrap.dedent(FAKE_CC_HOOKS), encoding="utf-8")
    monkeypatch.syspath_prepend(str(lib))
    monkeypatch.delitem(sys.modules, "cc_hooks", raising=False)
    yield
    sys.modules.pop("cc_hooks", None)


def test_writes_hook_test_fixtures_and_settings(tmp_path):
    out = tmp_path / "proj" / ".claude" / "hooks"
    rc, rep = run_json(mod, [spec(tmp_path), "--out", str(out)])
    assert rc == 0 and rep["warnings"] == []
    assert sorted(rep["written"]) == [
        "deny-env-read.py",
        "deny-env-read.settings.json",
        "fixtures/deny-env-read/match.json",
        "fixtures/deny-env-read/nomatch.json",
        "test_deny-env-read.py",
    ]
    settings = json.loads((out / "deny-env-read.settings.json").read_text(encoding="utf-8"))
    handler = settings["hooks"]["PreToolUse"][0]
    assert handler["matcher"] == "Bash"
    assert handler["hooks"][0]["args"] == ["${CLAUDE_PROJECT_DIR}/.claude/hooks/deny-env-read.py"]
    match = json.loads((out / "fixtures" / "deny-env-read" / "match.json").read_text(encoding="utf-8"))
    assert match["event"]["tool_input"] == {"command": "cat .env"} and match["expect"]["decision"] == "deny"
    for name in ("deny-env-read.py", "test_deny-env-read.py"):
        compile((out / name).read_text(encoding="utf-8"), name, "exec")
    assert b"\r\n" not in (out / "deny-env-read.py").read_bytes()


def test_generated_block_hook_denies_matches_and_fails_closed(tmp_path, monkeypatch, fake_cc_hooks):
    out = tmp_path / "hooks"
    run_main(mod, [spec(tmp_path), "--out", str(out)])
    hook = out / "deny-env-read.py"
    for fixture, expected in (("match", "deny"), ("nomatch", None)):
        case = json.loads((out / "fixtures" / "deny-env-read" / f"{fixture}.json").read_text(encoding="utf-8"))
        printed = run_hook(hook, case["event"], monkeypatch)
        decision = json.loads(printed)["hookSpecificOutput"]["permissionDecision"] if printed.strip() else None
        assert decision == expected
    printed = run_hook(hook, "not json", monkeypatch)
    assert json.loads(printed)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_modify_and_stop_hooks(tmp_path, monkeypatch, fake_cc_hooks):
    modify = SPEC.replace("action: block", "action: modify").replace("deny-env-read", "lease")
    modify = modify.replace(
        "pattern: (^|\\s)cat\\s+\\S*\\.env\\b", "pattern: --force\\b\nreplacement: --force-with-lease"
    )
    modify = modify.replace("cat .env", "git push --force").replace("ls -la", "git push")
    out = tmp_path / "hooks"
    rc, _, _ = run_main(mod, [spec(tmp_path, modify), "--out", str(out)])
    assert rc == 0
    printed = run_hook(
        out / "lease.py",
        {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git push --force origin"}},
        monkeypatch,
    )
    hso = json.loads(printed)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "ask" and hso["updatedInput"]["command"] == "git push --force-with-lease origin"
    stop = json.dumps(
        {
            "name": "summary",
            "event": "Stop",
            "action": "block",
            "pattern": "^$",
            "message": "Summarise what changed.",
            "match_example": "",
            "nomatch_example": "Done.",
        }
    )
    rc, _, _ = run_main(mod, [spec(tmp_path, stop, "stop.json"), "--out", str(out)])
    assert rc == 1  # a block hook that fails open is a warning
    printed = run_hook(
        out / "summary.py",
        {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": ""},
        monkeypatch,
    )
    assert json.loads(printed)["decision"] == "block"
    assert (
        run_hook(
            out / "summary.py",
            {"hook_event_name": "Stop", "stop_hook_active": True, "last_assistant_message": ""},
            monkeypatch,
        )
        == ""
    )


def test_warnings_exit_1(tmp_path):
    allow = SPEC.replace("action: block", "action: allow")
    rc, rep = run_json(mod, [spec(tmp_path, allow)])
    assert rc == 1 and any("allow skips" in w for w in rep["warnings"])
    post = SPEC.replace("event: PreToolUse", "event: PostToolUse")
    rc, rep = run_json(mod, [spec(tmp_path, post)])
    assert rc == 1 and any("PostToolUse" in w for w in rep["warnings"])


@pytest.mark.parametrize(
    "change, message",
    [
        (("event: PreToolUse", "event: Notification"), "event must be"),
        (("action: block", "action: delete"), "action must be"),
        (("event: PreToolUse\nmatcher: Bash", "event: SessionStart"), "not available"),
        (("pattern: (^|\\s)cat", "pattern: (cat"), "does not compile"),
        (("nomatch_example: ls -la", "nomatch_example: cat .env"), "nomatch_example matches"),
        (("match_example: cat .env", "match_example: ls"), "match_example does not match"),
        (("message: Reading", "message: Token is $API_TOKEN. Reading"), "environment variable"),
        (("name: deny-env-read\n", ""), "missing: name"),
    ],
)
def test_bad_specs_exit_2(tmp_path, change, message):
    rc, _, err = run_main(mod, [spec(tmp_path, SPEC.replace(*change))])
    assert rc == 2 and message in err


def test_empty_and_missing_spec_exit_2(tmp_path):
    rc, _, err = run_main(mod, [spec(tmp_path, "\n")])
    assert rc == 2 and "missing" in err
    rc, _, err = run_main(mod, [str(tmp_path / "none.txt")])
    assert rc == 2 and "not found" in err
    rc, _, err = run_main(mod, [spec(tmp_path, "this is not a spec", "bad.txt")])
    assert rc == 2 and "key: value" in err


def test_refuses_to_overwrite_without_force(tmp_path):
    out = tmp_path / "hooks"
    assert run_main(mod, [spec(tmp_path), "--out", str(out)])[0] == 0
    rc, _, err = run_main(mod, [spec(tmp_path), "--out", str(out)])
    assert rc == 2 and "--force" in err
    assert run_main(mod, [spec(tmp_path), "--out", str(out), "--force"])[0] == 0


def test_golden_printed_bundle(tmp_path):
    rc, out, _ = run_main(mod, [spec(tmp_path)])
    assert rc == 0
    assert out.startswith("# Hook scaffold\n\n## deny-env-read.py\n\n```python\n#!/usr/bin/env python3\n")
    assert "        deny(MESSAGE).exit()\n" in out
    assert '## deny-env-read.settings.json\n\n```json\n{\n  "hooks": {\n    "PreToolUse": [\n' in out
