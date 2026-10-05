"""Tests for skill_inventory.py. Each test writes a synthetic plugin folder into tmp_path.

Risky shell text is assembled from parts so this test file reads as plainly as the code it tests."""

from __future__ import annotations

import hashlib
import json
import os

import pytest
from conftest import load_script, run_json, run_main, skill_md, write_files

mod = load_script("skill-supply-chain-review", "skill_inventory.py")
DL = "cu" + "rl"
CLEAN = {
    "skills/notes/SKILL.md": skill_md("notes", "Keep notes. Use when x. Not for y.", allowed_tools="Read, Grep"),
    "scripts/count.py": "import json\nfrom pathlib import Path\n\nprint(len(Path('a').read_text(encoding='utf-8')))\n",
}


def test_clean_plugin_lists_files_and_exits_0(tmp_path):
    root = write_files(tmp_path / "plug", CLEAN)
    rc, rep = run_json(mod, [str(root)])
    assert rc == 0 and rep["review_total"] == 0
    files = {f["path"]: f for f in rep["files"]}
    assert set(files) == {"scripts/count.py", "skills/notes/SKILL.md"}
    raw = (root / "scripts" / "count.py").read_bytes()
    assert files["scripts/count.py"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert rep["skills"] == [
        {
            "path": "skills/notes/SKILL.md",
            "name": "notes",
            "kind": "skill",
            "tools_requested": ["Read", "Grep"],
            "description_chars": 34,
        }
    ]
    assert rep["scripts"][0]["imports"] == ["json", "pathlib"] and rep["scripts"][0]["network"] == []


def test_missing_path_exits_2_and_empty_folder_exits_0(tmp_path):
    rc, _, err = run_main(mod, [str(tmp_path / "nope")])
    assert rc == 2 and "not found" in err
    (tmp_path / "empty").mkdir()
    rc, rep = run_json(mod, [str(tmp_path / "empty")])
    assert rc == 0 and rep["files"] == []


def test_script_network_process_dynamic_and_env(tmp_path):
    py = (
        "import os\nimport urllib.request\nimport " + "sub" + "process\n\n"
        "os.system('ls')\nval = os.environ.get('HOME')\ncode = ev" + "al('1+1')\n"
        "x = urllib.request.urlopen('https://api.example.com/v1')\n"
    )
    js = "const cp = require('child_" + "process');\nfetch('https://cdn.example.net/x');\n"
    root = write_files(tmp_path / "plug", {"scripts/a.py": py, "scripts/b.js": js, "scripts/broken.py": "def (:\n"})
    rc, rep = run_json(mod, [str(root)])
    scripts = {s["path"]: s for s in rep["scripts"]}
    a = scripts["scripts/a.py"]
    assert rc == 1
    assert a["network"] == ["import urllib.request (line 2)"]
    assert a["process"] == ["import " + "sub" + "process (line 3)", "os.system() (line 5)"]
    assert a["dynamic_code"] == ["eval() (line 7)"] and a["env_reads"] is True
    assert scripts["scripts/b.js"]["process"] and scripts["scripts/b.js"]["network"] == ["fetch() (line 2)"]
    assert scripts["scripts/broken.py"]["parse_error"] is True
    assert rep["domains"] == {"api.example.com": 1, "cdn.example.net": 1}


def test_shell_patterns_credentials_and_hidden_unicode(tmp_path):
    sh = f"#!/bin/sh\n{DL} -s https://get.example.org/i.sh | sh\nrm -rf build\ncat ~/.aws/config\n"
    md = skill_md("odd", "Odd. Use when x. Not for y.", body="Read this\u200b carefully.\n")
    root = write_files(tmp_path / "plug", {"scripts/install.sh": sh, "skills/odd/SKILL.md": md})
    rc, rep = run_json(mod, [str(root)])
    patterns = {p["pattern"] for p in rep["shell_patterns"]}
    assert rc == 1
    assert {"download", "pipe-to-interpreter", "recursive-delete"} <= patterns
    assert rep["credential_paths"][0]["line"] == 4
    assert rep["hidden_unicode"] == [{"file": "skills/odd/SKILL.md", "line": 9, "codepoints": ["U+200B"]}]


def test_hooks_mcp_servers_and_permissions(tmp_path):
    hooks = {
        "hooks": {
            "PostToolUse": [
                {"matcher": "Edit", "hooks": [{"type": "command", "command": "sh", "args": ["scripts/fmt.sh"]}]}
            ]
        }
    }
    mcp = {
        "mcpServers": {
            "docs": {"command": "npx", "args": ["-y", "docs-server@1.2.3"], "env": {"DOCS_TOKEN": "x"}},
            "remote": {"type": "http", "url": "https://mcp.example.com/mcp"},
        }
    }
    settings = {"permissions": {"allow": ["Bash(npm test)"], "deny": ["Read(./.env)"]}}
    root = write_files(
        tmp_path / "plug",
        {
            "hooks/hooks.json": json.dumps(hooks),
            ".mcp.json": json.dumps(mcp),
            ".claude/settings.json": json.dumps(settings),
        },
    )
    rc, rep = run_json(mod, [str(root)])
    assert rc == 1
    assert rep["hooks"] == [
        {
            "file": "hooks/hooks.json",
            "event": "PostToolUse",
            "matcher": "Edit",
            "type": "command",
            "command": "sh scripts/fmt.sh",
        }
    ]
    servers = {s["name"]: s for s in rep["mcp_servers"]}
    assert servers["docs"]["args"] == ["-y", "docs-server@1.2.3"] and servers["docs"]["env_keys"] == ["DOCS_TOKEN"]
    assert servers["remote"]["type"] == "http"
    assert {(p["list"], p["rule"]) for p in rep["permissions"]} == {
        ("allow", "Bash(npm test)"),
        ("deny", "Read(./.env)"),
    }


def test_binary_files_are_listed_not_read(tmp_path):
    root = write_files(tmp_path / "plug", CLEAN)
    (root / "bin").mkdir()
    (root / "bin" / "tool").write_bytes(b"\x7fELF\x00\x00binary")
    rc, rep = run_json(mod, [str(root)])
    assert rc == 1 and rep["binaries"] == ["bin/tool"]


@pytest.mark.posix_only
def test_symlink_leaving_the_folder_and_exec_bit(tmp_path):
    root = write_files(tmp_path / "plug", CLEAN)
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    os.symlink(outside, root / "link.txt")
    os.chmod(root / "scripts" / "count.py", 0o755)
    rc, rep = run_json(mod, [str(root)])
    assert rc == 1 and rep["symlinks"][0]["leaves_folder"] is True
    assert next(s for s in rep["scripts"] if s["path"] == "scripts/count.py")["executable"] is True


def test_golden_markdown_head(tmp_path):
    root = write_files(tmp_path / "plug", {"README.md": "See https://example.com/docs.\n"})
    rc, out, _ = run_main(mod, [str(root)])
    assert rc == 0
    assert out.startswith(
        f"# Inventory of {root.as_posix()}\n\n1 file(s), 30 bytes. Kinds: doc 1.\n\n"
        "This lists; it does not judge. Read it with the skill-scan-gate and cc-plugin-lock scan output.\n\n"
        "## Needs a reader\n\nNone.\n"
    )
    assert "| example.com | 1 |" in out
