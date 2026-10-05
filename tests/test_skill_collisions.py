"""Tests for skill_collisions.py. Each test writes synthetic home, project and plugin folders into tmp_path."""

from __future__ import annotations

import json

from conftest import load_script, run_json, run_main, skill_md, write_files

mod = load_script("skill-collision-check", "skill_collisions.py")


def desc(topic: str) -> str:
    return f"Handle {topic}. Use when x. Not for y."


def found(rep: dict) -> set[tuple[str, str]]:
    return {(f["rule"], f["name"]) for f in rep["findings"]}


def test_no_location_exits_2_and_clean_folders_exit_0(tmp_path):
    rc, _, err = run_main(mod, [])
    assert rc == 2 and "at least one" in err
    rc, _, err = run_main(mod, ["--home", str(tmp_path / "missing")])
    assert rc == 2 and "not a folder" in err
    write_files(tmp_path / "home", {".claude/skills/alpha/SKILL.md": skill_md("alpha", desc("invoices"))})
    rc, rep = run_json(mod, ["--home", str(tmp_path / "home")])
    assert rc == 0 and rep["skills"] == 1 and rep["findings"] == []


def test_personal_shadows_project_and_managed_shadows_personal(tmp_path):
    write_files(tmp_path / "home", {".claude/skills/notes/SKILL.md": skill_md("notes", desc("meeting notes"))})
    write_files(tmp_path / "proj", {".claude/skills/notes/SKILL.md": skill_md("notes", desc("project notes"))})
    write_files(tmp_path / "managed", {"notes/SKILL.md": skill_md("notes", desc("company notes"))})
    rc, rep = run_json(mod, ["--home", str(tmp_path / "home"), "--project", str(tmp_path / "proj")])
    f = next(x for x in rep["findings"] if x["rule"] == "shadowed")
    assert rc == 1 and f["winner"].startswith("personal") and "project ignored" in f["detail"]
    _, rep = run_json(mod, ["--managed", str(tmp_path / "managed"), "--home", str(tmp_path / "home")])
    f = next(x for x in rep["findings"] if x["rule"] == "shadowed")
    assert f["winner"].startswith("managed")


def test_command_hidden_by_skill(tmp_path):
    write_files(
        tmp_path / "proj",
        {
            ".claude/skills/deploy/SKILL.md": skill_md("deploy", desc("deploys")),
            ".claude/commands/deploy.md": "Run it.",
        },
    )
    rc, rep = run_json(mod, ["--project", str(tmp_path / "proj")])
    assert rc == 1 and ("command-vs-skill", "deploy") in found(rep)


def test_plugin_duplicates_via_installed_index(tmp_path):
    a = write_files(tmp_path / "cache" / "mkt" / "pa" / "1.0.0", {"skills/lint/SKILL.md": skill_md("lint", desc("a"))})
    b = write_files(tmp_path / "cache" / "mkt" / "pb" / "2.0.0", {"skills/lint/SKILL.md": skill_md("lint", desc("b"))})
    write_files(tmp_path / "cache" / "mkt" / "pb" / "1.0.0", {"skills/old/SKILL.md": skill_md("old", desc("c"))})
    index = {"version": 2, "plugins": {"pa@mkt": [{"installPath": str(a)}], "pb@mkt": [{"installPath": str(b)}]}}
    (tmp_path / "installed_plugins.json").write_text(json.dumps(index), encoding="utf-8")
    rc, rep = run_json(mod, ["--plugins-root", str(tmp_path)])
    assert rc == 1 and ("plugin-duplicate", "lint") in found(rep)
    assert rep["skills"] == 2  # the stale 1.0.0 folder of pb is not installed, so it is not read
    f = next(x for x in rep["findings"] if x["rule"] == "plugin-duplicate")
    assert f["winner"] == "both load" and "pa:lint" in f["detail"] and "pb:lint" in f["detail"]


def test_cache_fallback_and_plugin_manifest_skills_folder(tmp_path):
    write_files(
        tmp_path / "cache" / "mkt" / "pc" / "1.0.0",
        {
            ".claude-plugin/plugin.json": json.dumps({"name": "pc", "skills": "./extra"}),
            "extra/tidy/SKILL.md": skill_md("tidy", desc("tidy")),
        },
    )
    write_files(tmp_path / "copy", {"tidy/SKILL.md": skill_md("tidy", desc("tidy copy"))})
    rc, rep = run_json(mod, ["--plugins-root", str(tmp_path), "--extra", f"copy={tmp_path / 'copy'}"])
    assert rc == 1 and ("plugin-duplicate", "tidy") in found(rep)


def test_duplicate_in_folder_builtin_names_and_overlap(tmp_path):
    write_files(
        tmp_path / "home",
        {
            ".claude/skills/review/SKILL.md": skill_md(
                "review", "Review release notes against the tag range and the changelog. Use when x. Not for y."
            ),
            ".claude/skills/review-copy/SKILL.md": skill_md("review", desc("copies")),
            ".claude/skills/notes/SKILL.md": skill_md(
                "notes", "Check release notes against the tag range and changelog entries. Use when x. Not for y."
            ),
        },
    )
    (tmp_path / "builtins.txt").write_text("/review\nhelp\n", encoding="utf-8")
    rc, rep = run_json(
        mod, ["--home", str(tmp_path / "home"), "--builtin-names", str(tmp_path / "builtins.txt"), "--overlap", "0.4"]
    )
    got = found(rep)
    assert rc == 1
    assert ("duplicate-in-folder", "review") in got
    assert ("builtin-name", "review") in got
    assert any(r == "description-overlap" and "notes" in n for r, n in got)


def test_overlap_threshold_and_cosine():
    a, b = mod.bag("release notes tag range"), mod.bag("release notes tag range")
    assert round(mod.cosine(a, b), 6) == 1.0
    assert mod.cosine(mod.bag("invoices"), mod.bag("kubernetes")) == 0.0
    assert mod.cosine(mod.bag(""), a) == 0.0


def test_golden_markdown(tmp_path):
    write_files(
        tmp_path / "proj", {".claude/skills/a/SKILL.md": skill_md("a", desc("x")), ".claude/commands/a.md": "x"}
    )
    rc, out, _ = run_main(mod, ["--project", str(tmp_path / "proj")])
    assert rc == 1
    skill_path = (tmp_path / "proj" / ".claude" / "skills" / "a" / "SKILL.md").as_posix()
    cmd_path = (tmp_path / "proj" / ".claude" / "commands" / "a.md").as_posix()
    assert out == (
        "# Skill collisions\n\n1 skill(s) and 1 command(s) read from: project:project. 1 finding(s).\n\n"
        "| Rule | Name | Wins | Detail |\n|---|---|---|---|\n"
        f"| command-vs-skill | a | skill ({skill_path}) | project command {cmd_path} is hidden by the skill |\n\n"
        f"## Paths\n\n- command-vs-skill a: `{cmd_path}`, `{skill_path}`\n"
    )
