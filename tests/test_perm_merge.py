"""Tests for perm_merge.py. Each test writes synthetic settings files and rule lists into tmp_path."""

from __future__ import annotations

import json

from conftest import load_script, run_json, run_main, write_files

mod = load_script("permissions-builder", "perm_merge.py")


def settings(**lists: list[str]) -> str:
    return json.dumps({"permissions": lists})


def rules(rep: dict) -> set[tuple[str, str]]:
    return {(f["rule"], f["item"]) for f in rep["findings"]}


def test_merges_dedupes_and_sorts_deny_first(tmp_path):
    write_files(
        tmp_path,
        {
            "team.txt": "# team rules\ndeny Bash(rm -rf *)\nallow Bash(npm run test *)\nallow  Bash(npm run test *) \n",
            "mcp.json": settings(allow=["mcp__docs__search"], ask=["mcp__docs__delete_page"]),
        },
    )
    rc, rep = run_json(mod, ["--source", str(tmp_path / "team.txt"), "--source", str(tmp_path / "mcp.json")])
    assert rc == 0 and rep["findings"] == []
    assert rep["merged"]["deny"] == ["Bash(rm -rf *)"]
    assert rep["merged"]["allow"] == ["Bash(npm run test *)", "mcp__docs__search"]
    assert rep["merged"]["ask"] == ["mcp__docs__delete_page"]


def test_conflicts_keep_the_stricter_list(tmp_path):
    write_files(
        tmp_path,
        {
            "a.json": settings(allow=["Bash(git push *)", "Read(./.env)"], ask=["Bash(npm publish)"]),
            "b.txt": "ask Bash(git push *)\ndeny Read(./.env)\ndeny Bash(npm publish)\n",
        },
    )
    rc, rep = run_json(mod, ["--source", str(tmp_path / "a.json"), "--source", str(tmp_path / "b.txt")])
    assert rc == 1
    assert rules(rep) == {
        ("conflict-allow-ask", "Bash(git push *)"),
        ("conflict-allow-deny", "Read(./.env)"),
        ("conflict-ask-deny", "Bash(npm publish)"),
    }
    assert rep["merged"] == {
        "deny": ["Bash(npm publish)", "Read(./.env)"],
        "ask": ["Bash(git push *)"],
        "allow": [],
    }


def test_broad_and_malformed_rules(tmp_path):
    write_files(
        tmp_path,
        {"s.json": settings(allow=["Bash(*)", "Read(**)", "mcp__github", "mcp__docs__*", "Edit(./src/**)", "bash ls"])},
    )
    rc, rep = run_json(mod, ["--source", str(tmp_path / "s.json")])
    assert rc == 1
    broad = {i for r, i in rules(rep) if r == "broad-allow"}
    assert broad == {"Bash(*)", "Read(**)", "mcp__github", "mcp__docs__*"}
    assert ("malformed-rule", "bash ls") in rules(rep)
    assert "bash ls" not in rep["merged"]["allow"]


def test_diff_against_current_and_replace_flags_removed_deny(tmp_path):
    write_files(
        tmp_path,
        {
            "current.json": json.dumps(
                {
                    "model": "x",
                    "permissions": {"allow": ["Bash(ls)"], "deny": ["Read(./secrets/**)"], "defaultMode": "default"},
                }
            ),
            "new.txt": "allow Bash(npm test)\n",
        },
    )
    rc, rep = run_json(mod, ["--source", str(tmp_path / "new.txt"), "--current", str(tmp_path / "current.json")])
    assert rc == 0
    assert rep["diff"]["allow"] == {"added": ["Bash(npm test)"], "removed": []}
    rc, rep = run_json(
        mod, ["--source", str(tmp_path / "new.txt"), "--current", str(tmp_path / "current.json"), "--replace"]
    )
    assert rc == 1 and ("deny-removed", "Read(./secrets/**)") in rules(rep)
    assert rep["diff"]["allow"]["removed"] == ["Bash(ls)"]


def test_emit_settings_keeps_other_keys_in_order(tmp_path):
    write_files(
        tmp_path,
        {
            "current.json": json.dumps(
                {"model": "x", "permissions": {"allow": ["Bash(ls)"], "defaultMode": "default"}, "env": {"A": "1"}}
            ),
            "new.txt": "deny Bash(rm -rf *)\n",
        },
    )
    target = tmp_path / "proposed.json"
    rc, out, _ = run_main(
        mod,
        [
            "--source",
            str(tmp_path / "new.txt"),
            "--current",
            str(tmp_path / "current.json"),
            "--emit",
            "settings",
            "--out",
            str(target),
        ],
    )
    assert rc == 0 and out == ""
    data = json.loads(target.read_text(encoding="utf-8"))
    assert list(data) == ["model", "permissions", "env"]
    assert list(data["permissions"]) == ["deny", "allow", "defaultMode"]
    assert data["permissions"]["deny"] == ["Bash(rm -rf *)"]


def test_bad_input_exits_2(tmp_path):
    write_files(tmp_path, {"bad.json": "{", "bad.txt": "permit Bash(ls)\n", "list.json": '{"allow": "Bash(ls)"}'})
    for name in ("bad.json", "bad.txt", "list.json", "missing.txt"):
        rc, _, err = run_main(mod, ["--source", str(tmp_path / name)])
        assert rc == 2 and err.startswith("perm_merge.py:"), name
    rc, _, err = run_main(mod, [])
    assert rc == 2 and "--source" in err


def test_empty_sources_give_empty_lists(tmp_path):
    write_files(tmp_path, {"empty.txt": "# nothing yet\n", "empty.json": "{}"})
    rc, rep = run_json(mod, ["--source", str(tmp_path / "empty.txt"), "--source", str(tmp_path / "empty.json")])
    assert rc == 0 and rep["merged"] == {"deny": [], "ask": [], "allow": []}


def test_golden_markdown(tmp_path):
    write_files(tmp_path, {"t.txt": "deny Read(./.env)\nallow Bash(npm test)\n"})
    rc, out, _ = run_main(mod, ["--source", str(tmp_path / "t.txt")])
    assert rc == 0
    assert out == (
        f"# Permission rules, merged\n\nSources: {tmp_path / 't.txt'}.\n\n"
        "## deny (1)\n\n- `Read(./.env)`\n\n## ask (0)\n\nNone.\n\n## allow (1)\n\n- `Bash(npm test)`\n\n"
        "## Changes against the current settings\n\nNo --current file; every rule is new.\n\n## Findings\n\nNone.\n"
    )
