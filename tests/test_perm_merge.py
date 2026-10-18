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


def test_unanchored_allow_globs_are_dropped_but_deny_globs_are_kept(tmp_path):
    write_files(tmp_path, {"s.json": settings(allow=["*", "B*", "mcp__*", "mcp__git*__x", "mcp__github__get_*"],
                                               deny=["*", "mcp__*"])})  # fmt: skip
    rc, rep = run_json(mod, ["--source", str(tmp_path / "s.json"), "--json"])
    ignored = {i for r, i in rules(rep) if r == "allow-glob-ignored"}
    assert rc == 1 and ignored == {"*", "B*", "mcp__*", "mcp__git*__x"}
    assert rep["merged"]["deny"] == ["*", "mcp__*"]
    assert rep["merged"]["allow"] == ["mcp__github__get_*"]
    assert not any(r == "malformed-rule" for r, _ in rules(rep))


def test_powershell_whole_tool_allows_are_broad(tmp_path):
    write_files(tmp_path, {"s.json": settings(allow=["PowerShell", "PowerShell(*)", "PowerShell(Get-ChildItem *)"])})
    _, rep = run_json(mod, ["--source", str(tmp_path / "s.json"), "--json"])
    assert {i for r, i in rules(rep) if r == "broad-allow"} == {"PowerShell", "PowerShell(*)"}


def test_wildcard_before_subcommand_and_literal_colon_star(tmp_path):
    write_files(
        tmp_path,
        {
            "s.json": settings(
                allow=["Bash(git * main)", "Bash(* --version)", "Bash(git log *)", "Bash(npm run test:*)"],
                ask=["Bash(git:* push)", "Bash(git * main)"],
            )
        },
    )
    rc, rep = run_json(mod, ["--source", str(tmp_path / "s.json"), "--json"])
    got = {(r, i) for r, i in rules(rep) if r in ("wildcard-before-subcommand", "colon-star-literal")}
    assert rc == 1 and got == {
        ("wildcard-before-subcommand", "Bash(* --version)"),
        ("colon-star-literal", "Bash(git:* push)"),
    }
    # the ask copy of Bash(git * main) wins over the allow copy, so only the ask stays and asks are not warned
    assert "Bash(git * main)" in rep["merged"]["ask"]


def test_text_source_that_is_not_utf8_exits_2(tmp_path):
    (tmp_path / "rules.txt").write_bytes(b"allow Bash(ls \xff)\n")
    rc, _, err = run_main(mod, ["--source", str(tmp_path / "rules.txt")])
    assert rc == 2 and "not UTF-8" in err
