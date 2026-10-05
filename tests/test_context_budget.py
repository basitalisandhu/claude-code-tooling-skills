"""Tests for context_budget.py. Each test writes a synthetic project (and home folder) into tmp_path."""

from __future__ import annotations

import json

from conftest import load_script, run_json, run_main, skill_md, write_files

mod = load_script("context-budget-audit", "context_budget.py")
AS_OF = ["--as-of", "2026-10-05"]
PARA = "Always run the formatter and the full test suite before you open a pull request in this repository."


def items(rep: dict) -> dict[str, dict]:
    return {i["item"]: i for i in rep["items"]}


def rules(rep: dict) -> set[tuple[str, str]]:
    return {(f["rule"], f["item"]) for f in rep["findings"]}


def test_empty_project_exits_0_with_zero_total(tmp_path):
    (tmp_path / "proj").mkdir()
    rc, rep = run_json(mod, [str(tmp_path / "proj"), *AS_OF])
    assert rc == 0 and rep["every_turn_tokens"] == 0 and rep["items"] == [] and rep["user_scope_read"] is False


def test_counts_memory_imports_rules_skills_and_mcp_tools(tmp_path):
    proj = write_files(
        tmp_path / "proj",
        {
            "CLAUDE.md": "# Project\n\nSee @docs/style.md for style.\n",
            "docs/style.md": "Use British spelling.\n",
            "AGENTS.md": "Agents read this.\n",
            "pkg/CLAUDE.md": "Package notes.\n",
            ".claude/rules/always.md": "Keep functions short.\n",
            ".claude/rules/py.md": "---\npaths: src/**/*.py\n---\nType hints.\n",
            ".claude/skills/plan-review/SKILL.md": skill_md("plan-review", "Review plans. Use when x. Not for y."),
            ".claude/settings.json": json.dumps({"hooks": {"SessionStart": [{"hooks": [{"type": "command"}]}]}}),
        },
    )
    tools = tmp_path / "tools.json"
    tools.write_text(
        json.dumps({"tools": [{"name": "get_item", "description": "Get one item.", "inputSchema": {}}]}),
        encoding="utf-8",
    )
    rc, rep = run_json(mod, [str(proj), "--mcp-tools", f"demo={tools}", *AS_OF])
    got = items(rep)
    assert got["./CLAUDE.md"]["load"] == "every turn"
    assert got["./docs/style.md"]["category"] == "import"
    assert got["./AGENTS.md"]["load"] == "not loaded"
    assert got["./pkg/CLAUDE.md"]["load"] == "on demand"
    assert got["./.claude/rules/always.md"]["load"] == "every turn"
    assert got["./.claude/rules/py.md"]["load"] == "conditional"
    assert got["plan-review (./.claude/skills/plan-review)"]["load"] == "every turn"
    assert got["mcp__demo__get_item"]["chars"] == len("get_item") + len("Get one item.") + 2
    assert any(i["category"] == "hooks" and i["load"] == "unknown" for i in rep["items"])
    assert rep["every_turn_tokens"] == sum(i["tokens"] for i in rep["items"] if i["load"] == "every turn")
    assert rc == 0


def test_agents_md_counts_when_imported(tmp_path):
    proj = write_files(tmp_path / "p", {"CLAUDE.md": "@AGENTS.md\n", "AGENTS.md": "Shared agent notes.\n"})
    _, rep = run_json(mod, [str(proj), *AS_OF])
    assert items(rep)["./AGENTS.md"]["load"] == "every turn"


def test_duplicates_stale_paths_dates_and_missing_imports(tmp_path):
    proj = write_files(
        tmp_path / "p",
        {
            "CLAUDE.md": f"{PARA}\n\nRun `scripts/deploy.sh` to ship.\n\n## Notes 2024-01-10\n\n@missing/file.md\n",
            ".claude/rules/dup.md": f"{PARA}\n",
            ".claude/rules/same.md": "Identical text.\n",
            ".claude/rules/same2.md": "Identical   text.\n",
        },
    )
    rc, rep = run_json(mod, [str(proj), *AS_OF])
    assert rc == 1
    found = rules(rep)
    assert ("duplicate-block", "./CLAUDE.md") in found or ("duplicate-block", "./.claude/rules/dup.md") in found
    assert ("duplicate-file", "./.claude/rules/same2.md") in found
    assert ("stale-path", "./CLAUDE.md") in found
    assert ("stale-date", "./CLAUDE.md") in found
    assert ("missing-import", (proj / "CLAUDE.md").as_posix()) in found


def test_large_item_truncated_description_and_budget(tmp_path):
    proj = write_files(
        tmp_path / "p",
        {
            "CLAUDE.md": "x" * 900 + "\n",
            ".claude/skills/long/SKILL.md": skill_md("long", "Review " + "a" * 1600 + ". Use when x. Not for y."),
        },
    )
    rc, rep = run_json(mod, [str(proj), "--max-item-tokens", "200", "--budget", "300", *AS_OF])
    assert rc == 1
    names = {f["rule"] for f in rep["findings"]}
    assert {"large-item", "description-truncated", "over-budget"} <= names
    assert items(rep)["long (./.claude/skills/long)"]["chars"] == 1536


def test_home_scope_and_plugin_cache(tmp_path):
    proj = write_files(tmp_path / "p", {"CLAUDE.md": "Project.\n"})
    home = write_files(
        tmp_path / "home",
        {
            ".claude/CLAUDE.md": "Personal.\n",
            ".claude/plugins/cache/mkt/tools/1.0.0/skills/lint/SKILL.md": skill_md("lint", "Lint. Use when x. Not y."),
        },
    )
    _, rep = run_json(mod, [str(proj), "--home", str(home), *AS_OF])
    got = items(rep)
    assert rep["user_scope_read"] is True and "~/.claude/CLAUDE.md" in got
    assert "lint (~/.claude/plugins/cache/mkt/tools/1.0.0/skills/lint)" in got


def test_bad_input_exits_2(tmp_path):
    rc, _, err = run_main(mod, [str(tmp_path / "missing")])
    assert rc == 2 and "not a folder" in err
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    rc, _, err = run_main(mod, [str(tmp_path), "--mcp-tools", f"x={tmp_path / 'bad.json'}"])
    assert rc == 2 and "tools/list" in err
    rc, _, err = run_main(mod, [str(tmp_path), "--as-of", "yesterday"])
    assert rc == 2


def test_golden_markdown(tmp_path):
    proj = write_files(tmp_path / "p", {"CLAUDE.md": "a" * 40 + "\n"})
    rc, out, _ = run_main(mod, [str(proj), *AS_OF])
    assert rc == 0
    assert out == (
        "# Context budget\n\nEvery turn: about 11 tokens (41 characters; tokens = characters / 4, rounded up).\n"
        "User scope (~/.claude) was not read; pass --home to include it.\n\n"
        "| Category | Tokens |\n|---|---|\n| memory | 11 |\n\n"
        "## Largest every-turn items (top 15)\n\n| # | Item | Category | Tokens |\n|---|---|---|---|\n"
        "| 1 | ./CLAUDE.md | memory | 11 |\n\n## Findings\n\nNone.\n"
    )
