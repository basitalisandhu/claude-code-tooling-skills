"""Tests for unattended_preflight.py.

Each test writes a synthetic project (settings files) and a synthetic session log or call list into tmp_path.
Paths in the logs are built from tmp_path at run time; nothing is read from the real home folder.
"""

from __future__ import annotations

import json

from conftest import load_script, run_json, run_main, write_files

mod = load_script("unattended-run-preflight", "unattended_preflight.py")

SETTINGS = {
    "permissions": {
        "allow": ["Bash(npm run *)", "mcp__github__get_issue", "WebFetch(domain:api.github.com)"],
        "ask": ["Bash(git push *)"],
        "deny": ["Read(./.env)", "Bash(curl *)"],
    }
}


def project(tmp_path, settings=None, local=None):
    files = {"proj/.claude/settings.json": json.dumps(settings if settings is not None else SETTINGS)}
    if local is not None:
        files["proj/.claude/settings.local.json"] = json.dumps(local)
    write_files(tmp_path, files)
    return tmp_path / "proj"


def tool_use(i, name, inp):
    return {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "id": f"t{i}", "name": name, "input": inp}]},
    }


def transcript(tmp_path, records):
    path = tmp_path / "run.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


def calls_file(tmp_path, calls):
    path = tmp_path / "calls.json"
    path.write_text(json.dumps(calls), encoding="utf-8")
    return path


def by_call(report):
    return {c["call"]: c for c in report["calls"]}


def test_allowed_compound_and_wrapper_run(tmp_path):
    proj = project(tmp_path)
    log = transcript(
        tmp_path,
        [
            {"type": "user", "message": {"role": "user", "content": "go"}},
            tool_use(1, "Bash", {"command": "git status && npm run build"}),
            tool_use(2, "Bash", {"command": "timeout 60 npm run test"}),
        ],
    )
    rc, report = run_json(mod, ["--project", str(proj), "--transcript", str(log)])
    assert rc == 0
    assert report["summary"] == {
        "calls": 2,
        "distinct": 2,
        "runs": 2,
        "needs_approval": 0,
        "denied": 0,
        "observed_refusals": 0,
    }


def test_compound_with_unallowed_part_needs_approval(tmp_path):
    proj = project(tmp_path)
    calls = calls_file(tmp_path, [{"tool": "Bash", "input": {"command": "npm run build && make deploy"}}])
    rc, report = run_json(mod, ["--project", str(proj), "--calls", str(calls)])
    assert rc == 1
    call = report["calls"][0]
    assert call["outcome"] == "needs-approval"
    assert "make deploy" in call["reason"]
    assert report["proposed"]["allow"] == ["Bash(make deploy *)"]


def test_deny_beats_allow_and_matches_past_assignment(tmp_path):
    settings = {"permissions": {"allow": ["Bash(curl *)"], "deny": ["Bash(curl *)"]}}
    proj = project(tmp_path, settings)
    calls = calls_file(tmp_path, [{"tool": "Bash", "input": {"command": "TOKEN=x curl https://example.com"}}])
    rc, report = run_json(mod, ["--project", str(proj), "--calls", str(calls)])
    assert rc == 1
    assert report["calls"][0]["outcome"] == "denied"
    assert report["calls"][0]["rule"] == "Bash(curl *)"


def test_allow_does_not_match_past_assignment(tmp_path):
    proj = project(tmp_path)
    calls = calls_file(tmp_path, [{"tool": "Bash", "input": {"command": "FOO=bar npm run build"}}])
    rc, report = run_json(mod, ["--project", str(proj), "--calls", str(calls)])
    assert rc == 1 and report["calls"][0]["outcome"] == "needs-approval"


def test_ask_rule_goes_to_decide_list(tmp_path):
    proj = project(tmp_path)
    calls = calls_file(tmp_path, [{"tool": "Bash", "input": {"command": "git push origin main"}}])
    rc, report = run_json(mod, ["--project", str(proj), "--calls", str(calls)])
    assert rc == 1
    assert report["calls"][0]["rule"] == "Bash(git push *)"
    assert report["proposed"]["allow"] == []


def test_mcp_tools_exact_allow_and_write_tool_to_decide(tmp_path):
    proj = project(tmp_path)
    log = transcript(
        tmp_path,
        [
            tool_use(1, "mcp__github__get_issue", {"issue": 1}),
            tool_use(2, "mcp__github__add_issue_comment", {"issue": 1, "body": "x"}),
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "t2",
                            "is_error": True,
                            "content": "Claude requested permissions to use mcp__github__add_issue_comment, "
                            "but you haven't granted it yet.",
                        }
                    ]
                },
            },
            tool_use(3, "mcp__linear__list_issues", {}),
        ],
    )
    rc, report = run_json(mod, ["--project", str(proj), "--transcript", str(log)])
    assert rc == 1
    calls = by_call(report)
    assert calls["mcp__github__get_issue"]["outcome"] == "runs"
    assert calls["mcp__github__add_issue_comment"]["observed_refusal"] is True
    assert report["proposed"]["decide"] == ["mcp__github__add_issue_comment"]
    assert report["proposed"]["allow"] == ["mcp__linear__list_issues"]


def test_unanchored_mcp_allow_glob_is_ignored(tmp_path):
    proj = project(tmp_path, {"permissions": {"allow": ["mcp__*", "mcp__linear__list_*"]}})
    calls = calls_file(tmp_path, [{"tool": "mcp__github__get_issue"}, {"tool": "mcp__linear__list_issues"}])
    rc, report = run_json(mod, ["--project", str(proj), "--calls", str(calls)])
    calls_ = by_call(report)
    assert calls_["mcp__github__get_issue"]["outcome"] == "needs-approval"
    assert calls_["mcp__linear__list_issues"]["outcome"] == "runs"
    assert rc == 1


def test_paths_reads_inside_run_edits_need_rule_and_deny(tmp_path):
    proj = project(tmp_path)
    calls = calls_file(
        tmp_path,
        [
            {"tool": "Read", "input": {"file_path": str(proj / "src" / "app.py")}},
            {"tool": "Read", "input": {"file_path": str(proj / ".env")}},
            {"tool": "Read", "input": {"file_path": str(tmp_path / "elsewhere" / "notes.txt")}},
            {"tool": "Write", "input": {"file_path": str(proj / "reports" / "nightly.md")}},
        ],
    )
    rc, report = run_json(mod, ["--project", str(proj), "--calls", str(calls)])
    assert rc == 1
    calls_ = by_call(report)
    assert calls_["Read: ./src/app.py"]["outcome"] == "runs"
    assert calls_["Read: ./.env"]["outcome"] == "denied"
    assert any(c.startswith("Read: ") and c.endswith("elsewhere/notes.txt") for c in calls_)
    assert calls_["Write: ./reports/nightly.md"]["outcome"] == "needs-approval"
    assert "Edit(./reports/**)" in report["proposed"]["allow"]


def test_accept_edits_and_dont_ask_modes(tmp_path):
    proj = project(tmp_path)
    calls = calls_file(tmp_path, [{"tool": "Edit", "input": {"file_path": str(proj / "a.txt")}}])
    rc, report = run_json(mod, ["--project", str(proj), "--calls", str(calls), "--mode", "acceptEdits"])
    assert rc == 0
    rc, out, _ = run_main(mod, ["--project", str(proj), "--calls", str(calls), "--mode", "dontAsk"])
    assert rc == 1 and "refused without asking (dontAsk)" in out


def test_webfetch_domain_rules(tmp_path):
    proj = project(tmp_path, {"permissions": {"allow": ["WebFetch(domain:*.example.org)"]}})
    calls = calls_file(
        tmp_path,
        [
            {"tool": "WebFetch", "input": {"url": "https://docs.example.org/x"}},
            {"tool": "WebFetch", "input": {"url": "https://example.org/x"}},
        ],
    )
    rc, report = run_json(mod, ["--project", str(proj), "--calls", str(calls)])
    calls_ = by_call(report)
    assert calls_["WebFetch: https://docs.example.org/x"]["outcome"] == "runs"
    assert calls_["WebFetch: https://example.org/x"]["outcome"] == "needs-approval"
    assert report["proposed"]["allow"] == ["WebFetch(domain:example.org)"]


def test_command_substitution_and_runner_rules_are_flagged(tmp_path):
    proj = project(tmp_path)
    calls = calls_file(
        tmp_path,
        [
            {"tool": "Bash", "input": {"command": "echo $(npm run build)"}},
            {"tool": "Bash", "input": {"command": "python3 scripts/report.py --week 42"}},
            {"tool": "Bash", "input": {"command": "gh issue list --state open"}},
        ],
    )
    rc, report = run_json(mod, ["--project", str(proj), "--calls", str(calls)])
    assert rc == 1
    assert by_call(report)["Bash: echo $(npm run build)"]["outcome"] == "needs-approval"
    assert "Bash(python3 scripts/report.py --week 42)" in report["proposed"]["decide"]
    assert "Bash(gh issue list *)" in report["proposed"]["allow"]


def test_redirect_target_checked_as_edit(tmp_path):
    proj = project(tmp_path, {"permissions": {"allow": ["Bash(npm run *)", "Edit(./build/**)"]}})
    calls = calls_file(
        tmp_path,
        [
            {"tool": "Bash", "input": {"command": "npm run build > build/log.txt"}},
            {"tool": "Bash", "input": {"command": "npm run build 2>/dev/null"}},
            {"tool": "Bash", "input": {"command": "npm run build > out.txt"}},
        ],
    )
    rc, report = run_json(mod, ["--project", str(proj), "--calls", str(calls)])
    calls_ = by_call(report)
    assert calls_["Bash: npm run build > build/log.txt"]["outcome"] == "runs"
    assert calls_["Bash: npm run build 2>/dev/null"]["outcome"] == "runs"
    assert calls_["Bash: npm run build > out.txt"]["outcome"] == "needs-approval"
    assert "Edit(./out.txt)" in report["proposed"]["allow"]
    assert rc == 1


def test_scopes_merge_and_emit_rules(tmp_path):
    proj = project(
        tmp_path, {"permissions": {"allow": ["Bash(make *)"]}}, local={"permissions": {"deny": ["Bash(make deploy *)"]}}
    )
    calls = calls_file(tmp_path, [{"tool": "Bash", "input": {"command": "make deploy"}}, {"tool": "WebSearch"}])
    rc, out, _ = run_main(mod, ["--project", str(proj), "--calls", str(calls), "--emit-rules"])
    assert rc == 1
    assert json.loads(out) == {"permissions": {"allow": ["WebSearch"]}}


def test_duplicate_calls_are_counted(tmp_path):
    proj = project(tmp_path)
    log = transcript(tmp_path, [tool_use(i, "Bash", {"command": "npm run lint"}) for i in range(3)])
    rc, report = run_json(mod, ["--project", str(proj), "--transcript", str(log)])
    assert rc == 0
    assert report["summary"]["calls"] == 3 and report["summary"]["distinct"] == 1


def test_markdown_report_sections(tmp_path):
    proj = project(tmp_path)
    calls = calls_file(tmp_path, [{"tool": "Bash", "input": {"command": "gh pr list"}}])
    rc, out, _ = run_main(mod, ["--project", str(proj), "--calls", str(calls)])
    assert rc == 1
    for heading in ("# Unattended run preflight", "## Calls that would stop the run", "## Proposed allow rules"):
        assert heading in out
    assert "`Bash(gh pr list *)`" in out


def test_malformed_transcript_line_exits_2(tmp_path):
    proj = project(tmp_path)
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"type": "assistant"}\n{not json\n', encoding="utf-8")
    rc, _, err = run_main(mod, ["--project", str(proj), "--transcript", str(bad)])
    assert rc == 2 and "line 2" in err


def test_bad_inputs_exit_2(tmp_path):
    proj = project(tmp_path, {"permissions": {"allow": "Bash(ls *)"}})
    calls = calls_file(tmp_path, [{"tool": "Bash", "input": {"command": "ls"}}])
    assert run_main(mod, ["--project", str(proj), "--calls", str(calls)])[0] == 2
    good = project(tmp_path / "g")
    assert run_main(mod, ["--project", str(good), "--calls", str(tmp_path / "missing.json")])[0] == 2
    not_list = tmp_path / "obj.json"
    not_list.write_text('{"tool": "Bash"}', encoding="utf-8")
    assert run_main(mod, ["--project", str(good), "--calls", str(not_list)])[0] == 2
    empty = tmp_path / "empty.jsonl"
    empty.write_text('{"type": "user", "message": {"content": "hi"}}\n', encoding="utf-8")
    rc, _, err = run_main(mod, ["--project", str(good), "--transcript", str(empty)])
    assert rc == 2 and "no tool calls" in err
    broken = tmp_path / "broken"
    write_files(broken, {".claude/settings.json": "{ not json"})
    assert run_main(mod, ["--project", str(broken), "--calls", str(calls)])[0] == 2


def test_help_documents_exit_codes():
    rc, out, _ = run_main(mod, ["--help"])
    assert rc == 0 and "usage:" in out and "Exit codes: 0" in out
