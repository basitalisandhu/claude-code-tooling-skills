"""Tests for subagent_scope.py.

Each test writes synthetic agent files (and, where needed, an .mcp.json) into tmp_path. Agent names, servers and
packages are made up.
"""

from __future__ import annotations

import json

from conftest import load_script, run_json, run_main, write_files

mod = load_script("subagent-tool-scope-review", "subagent_scope.py")

MCP = json.dumps({"mcpServers": {"github": {"type": "http", "url": "https://mcp.example.com/"}, "pg": {}}})


def agent(name, description, extra=""):
    return f"---\nname: {name}\ndescription: {description}\n{extra}---\n\nBody.\n"


def project(tmp_path, agents: dict[str, str], mcp=True):
    files = {f"proj/.claude/agents/{k}.md": v for k, v in agents.items()}
    if mcp:
        files["proj/.mcp.json"] = MCP
    write_files(tmp_path, files)
    return tmp_path / "proj"


def findings(report, name=None):
    return [
        (f["rule"], f["severity"]) for a in report["agents"] if name is None or a["name"] == name for f in a["findings"]
    ]


def args(proj, *more):
    return ["--project", str(proj), "--mcp", str(proj / ".mcp.json"), *more]


def test_scoped_reader_is_clean(tmp_path):
    proj = project(tmp_path, {"explorer": agent("explorer", "Explores the codebase.", "tools: Read, Grep, Glob\n")})
    rc, report = run_json(mod, args(proj))
    assert rc == 0
    a = report["agents"][0]
    assert a["effective"]["builtins"] == ["Glob", "Grep", "Read"]
    assert a["effective"]["writes"] is False and a["effective"]["mcp"] == []
    assert findings(report) == []


def test_missing_tools_inherits_everything_including_mcp(tmp_path):
    proj = project(tmp_path, {"code-reviewer": agent("code-reviewer", "Reviews diffs for bugs.")})
    rc, report = run_json(mod, args(proj))
    assert rc == 1
    assert ("inherits-all-tools", "high") in findings(report)
    a = report["agents"][0]
    assert a["inherits_all"] is True
    assert a["effective"]["mcp"] == ["mcp__github__* (inherited)", "mcp__pg__* (inherited)"]
    assert a["effective"]["suggested_tools"] == ["Read", "Grep", "Glob"]


def test_inheriting_writer_is_medium_and_disallowed_mcp_removes_servers(tmp_path):
    proj = project(
        tmp_path,
        {
            "builder": agent("builder", "Implements features."),
            "local-only": agent("local-only", "Implements features offline.", "disallowedTools: mcp__*\n"),
        },
    )
    rc, report = run_json(mod, args(proj, "--fail-on", "medium"))
    assert rc == 1
    assert findings(report, "builder") == [("inherits-all-tools", "medium")]
    local = next(a for a in report["agents"] if a["name"] == "local-only")
    assert local["effective"]["mcp"] == [] and local["effective"]["inherits_mcp"] is False


def test_lookalike_field_is_flagged_high(tmp_path):
    proj = project(
        tmp_path, {"r": agent("researcher", "Researches docs on the web.", "allowed-tools: Read, WebFetch\n")}
    )
    rc, report = run_json(mod, args(proj))
    assert rc == 1
    assert ("lookalike-field", "high") in findings(report)
    assert report["agents"][0]["effective"]["suggested_tools"] == ["Read", "Grep", "Glob", "WebFetch", "WebSearch"]


def test_reader_with_write_tools_and_block_list(tmp_path):
    text = "---\nname: auditor\ndescription: Audits configuration files.\ntools:\n  - Read\n  - Write\n  - Bash\n---\n"
    proj = project(tmp_path, {"auditor": text})
    rc, report = run_json(mod, args(proj))
    assert rc == 1
    assert ("read-only-job-with-write-tools", "high") in findings(report)
    assert report["agents"][0]["effective"]["builtins"] == ["Bash", "Read", "Write"]


def test_bypass_mode_and_server_wide_grants(tmp_path):
    proj = project(
        tmp_path,
        {
            "rel": agent(
                "release-manager",
                "Publishes releases.",
                "tools: Read, mcp__github__*, mcp__*\npermissionMode: bypassPermissions\n",
            )
        },
    )
    rc, report = run_json(mod, args(proj))
    assert rc == 1
    got = findings(report)
    assert ("bypass-mode", "high") in got
    assert ("server-wide-mcp-grant", "medium") in got and ("server-wide-mcp-grant", "high") in got


def test_named_mcp_tool_is_not_server_wide(tmp_path):
    proj = project(tmp_path, {"t": agent("triager", "Labels new issues.", "tools: Read, mcp__github__get_issue\n")})
    rc, report = run_json(mod, args(proj, "--fail-on", "low"))
    assert rc == 0
    assert report["agents"][0]["effective"]["mcp"] == ["mcp__github__get_issue"]


def test_inline_mcp_server_and_specifiers(tmp_path):
    extra = (
        "tools: Read, Bash(npm test *)\n"
        "disallowedTools: Write(./dist/**)\n"
        "mcpServers:\n"
        "  - playwright:\n"
        "      type: stdio\n"
        "      command: npx\n"
        '      args: ["-y", "@example/browser-mcp@latest"]\n'
        "  - github\n"
    )
    proj = project(tmp_path, {"bt": agent("browser-tester", "Tests features in a browser.", extra)})
    rc, report = run_json(mod, args(proj, "--fail-on", "medium"))
    assert rc == 1
    got = findings(report)
    assert ("inline-mcp-server", "medium") in got
    assert ("specifier-in-tools", "medium") in got
    assert ("disallowed-specifier", "info") in got
    a = report["agents"][0]
    assert "Bash" in a["effective"]["builtins"]
    assert a["effective"]["mcp"] == ["mcp__playwright__* (mcpServers)", "mcp__github__* (mcpServers)"]


def test_plugin_agents_ignore_some_fields(tmp_path):
    write_files(
        tmp_path,
        {
            "plug/agents/a.md": agent(
                "helper", "Answers questions.", "tools: Read\npermissionMode: plan\nhooks:\n  Stop: []\n"
            )
        },
    )
    rc, report = run_json(mod, ["--plugin", str(tmp_path / "plug"), "--fail-on", "low"])
    assert rc == 1
    assert sorted(findings(report)) == [("plugin-ignored-field", "low"), ("plugin-ignored-field", "low")]
    assert report["agents"][0]["file"] == "plugin:agents/a.md"


def test_malformed_agent_file_is_a_finding(tmp_path):
    proj = project(tmp_path, {"broken": "no front matter here\n", "open": "---\nname: open\n"})
    rc, report = run_json(mod, args(proj, "--fail-on", "low"))
    assert rc == 1
    assert [f["rule"] for a in report["agents"] for f in a["findings"]] == ["invalid-file", "invalid-file"]


def test_markdown_output(tmp_path):
    proj = project(tmp_path, {"code-reviewer": agent("code-reviewer", "Reviews diffs.")})
    rc, out, _ = run_main(mod, args(proj))
    assert rc == 1
    assert "# Subagent tool scope review" in out
    assert "| `code-reviewer` | project | all (inherited) |" in out
    assert "MCP servers known: github, pg." in out


def test_bad_inputs_exit_2(tmp_path):
    assert run_main(mod, [])[0] == 2
    assert run_main(mod, ["--project", str(tmp_path / "missing")])[0] == 2
    proj = project(tmp_path, {"a": agent("a", "Reviews.", "tools: Read\n")})
    bad = tmp_path / "bad.json"
    bad.write_text("{ nope", encoding="utf-8")
    assert run_main(mod, ["--project", str(proj), "--mcp", str(bad)])[0] == 2
    assert run_main(mod, ["--project", str(proj), "--mcp", str(tmp_path / "none.json")])[0] == 2
    wrong = tmp_path / "wrong.json"
    wrong.write_text('{"mcpServers": ["github"]}', encoding="utf-8")
    assert run_main(mod, ["--project", str(proj), "--mcp", str(wrong)])[0] == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    rc, _, err = run_main(mod, ["--project", str(empty)])
    assert rc == 2 and "no agent files" in err


def test_claude_json_projects_entry(tmp_path):
    proj = project(tmp_path, {"a": agent("writer", "Writes docs.")}, mcp=False)
    cfg = tmp_path / "claude.json"
    cfg.write_text(
        json.dumps({"mcpServers": {"slack": {}}, "projects": {str(proj.resolve()): {"mcpServers": {"jira": {}}}}}),
        encoding="utf-8",
    )
    rc, report = run_json(mod, ["--project", str(proj), "--mcp", str(cfg)])
    assert report["servers"] == ["slack", "jira"]
    assert rc == 0  # an inheriting writer is medium, below the default --fail-on high


def test_help_documents_exit_codes():
    rc, out, _ = run_main(mod, ["--help"])
    assert rc == 0 and "usage:" in out and "Exit codes: 0" in out
