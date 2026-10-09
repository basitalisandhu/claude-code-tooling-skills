"""Tests for portability_check.py. Each test writes a synthetic skill folder into tmp_path."""

from __future__ import annotations

import os

import pytest
from conftest import load_script, run_json, run_main, skill_md, write_files

mod = load_script("skill-portability-check", "portability_check.py")
GOOD_SKILL = skill_md(
    "tool",
    "Do a thing. Use when x. Not for y.",
    body='## Script\n\n```bash\npython3 "${CLAUDE_PLUGIN_ROOT}/skills/tool/scripts/run.py"\n```\n\n'
    "From a copy install, run `scripts/run.py` from the skill folder instead.\n",
)
GOOD_PY = 'from pathlib import Path\n\nprint(Path("a.txt").read_text(encoding="utf-8"))\n'


def rules(rep: dict) -> set[tuple[str, str]]:
    return {(f["file"].split("/", 1)[1], f["rule"]) for f in rep["findings"]}


def test_clean_skill_exits_0(tmp_path):
    write_files(tmp_path / "tool", {"SKILL.md": GOOD_SKILL, "scripts/run.py": GOOD_PY})
    rc, rep = run_json(mod, [str(tmp_path / "tool")])
    assert rc == 0 and rep["findings"] == [] and rep["files_checked"] == 2


def test_missing_path_exits_2_and_empty_folder_exits_0(tmp_path):
    rc, _, err = run_main(mod, [str(tmp_path / "nope")])
    assert rc == 2 and "not found" in err
    (tmp_path / "empty").mkdir()
    rc, rep = run_json(mod, [str(tmp_path / "empty")])
    assert rc == 0 and rep["files_checked"] == 0


def test_skill_md_rules(tmp_path):
    bad = (
        "---\nname: tool\ndescription: Do things: badly. Use when x. Not for y.\n---\n\n"
        '```bash\npython3 "${CLAUDE_PLUGIN_ROOT}/skills/tool/scripts/run.py"\nsed -i "s/a/b/" f.txt\n'
        "readlink -f x\n```\n\nSee /Users/alex/notes and scripts\\run.py and /opt/homebrew/bin.\n"
    )
    write_files(tmp_path / "tool", {"SKILL.md": bad})
    rc, rep = run_json(mod, [str(tmp_path / "tool")])
    assert rc == 1
    assert rules(rep) == {
        ("SKILL.md", "yaml-unsafe"),
        ("SKILL.md", "plugin-root-no-fallback"),
        ("SKILL.md", "non-portable-shell"),
        ("SKILL.md", "hardcoded-home-path"),
        ("SKILL.md", "windows-separator"),
        ("SKILL.md", "platform-path"),
    }
    lines = {f["line"] for f in rep["findings"] if f["rule"] == "non-portable-shell"}
    assert lines == {8, 9}


def test_python_command_rule(tmp_path):
    skill = skill_md(
        "tool",
        "Do a thing. Use when x. Not for y.",
        body=("## Commands\n\n```bash\npython x.py\npython3 x.py\npython3.12 -m venv .venv\n```\n"),
    )
    write_files(tmp_path / "tool", {"SKILL.md": skill})
    rc, rep = run_json(mod, [str(tmp_path / "tool")])
    assert rc == 1
    assert [
        (f["line"], f["rule"])
        for f in rep["findings"]
        if f["rule"] == "python-command"
    ] == [(12, "python-command")]


def test_python_rules(tmp_path):
    py = (
        "import os\nimport fcntl\nfrom pathlib import Path\n\n"
        "data = open('a.txt').read()\nraw = open('a.bin', 'rb').read()\nPath('b').write_text('x')\n"
        "Path('c').read_text(encoding='utf-8')\nuid = os.getuid()\n"
        "if os.name == 'posix':\n    gid = os.getgid()\n"
        "root = os.environ['CLAUDE_PLUGIN_ROOT']\nhelper = 'scripts\\\\helper.py'\n"
    )
    write_files(tmp_path / "tool", {"scripts/run.py": py})
    _, rep = run_json(mod, [str(tmp_path / "tool")])
    got = sorted((f["line"], f["rule"]) for f in rep["findings"])
    assert got == [
        (2, "os-specific-call"),
        (5, "open-no-encoding"),
        (7, "open-no-encoding"),
        (9, "os-specific-call"),
        (12, "env-no-default"),
        (13, "windows-separator"),
    ]


def test_shell_rules_and_shebangs(tmp_path):
    write_files(
        tmp_path / "tool",
        {
            "scripts/a.sh": "#!/bin/sh\nif [[ -n x ]]; then echo -e 'x'; fi\n",
            "scripts/b.sh": "#!/bin/bash\ndate -d yesterday\n",
            "scripts/c.sh": "#!/usr/bin/env bash\nprintf '%s\\n' ok\n",
        },
    )
    _, rep = run_json(mod, [str(tmp_path / "tool")])
    assert rules(rep) == {
        ("scripts/a.sh", "bashism-in-sh"),
        ("scripts/a.sh", "non-portable-shell"),
        ("scripts/b.sh", "shebang-hardcoded"),
        ("scripts/b.sh", "non-portable-shell"),
    }


def test_crlf_and_case_collision(tmp_path):
    folder = tmp_path / "tool"
    folder.mkdir()
    (folder / "SKILL.md").write_bytes(GOOD_SKILL.replace("\n", "\r\n").encode("utf-8"))
    (folder / "scripts").mkdir()
    (folder / "scripts" / "run.py").write_bytes(GOOD_PY.encode("utf-8"))
    names = {"Notes.md", "notes.md"}
    for n in names:
        (folder / n).write_text("x\n", encoding="utf-8")
    _, rep = run_json(mod, [str(folder)])
    got = rules(rep)
    assert ("SKILL.md", "crlf") in got
    if len({p.name for p in folder.iterdir()} & names) == 2:  # case-sensitive file system
        assert any(r == "case-collision" for _, r in got)


@pytest.mark.posix_only
def test_symlink_is_reported(tmp_path):
    write_files(tmp_path / "tool", {"SKILL.md": GOOD_SKILL, "scripts/run.py": GOOD_PY})
    os.symlink(tmp_path / "tool" / "scripts" / "run.py", tmp_path / "tool" / "scripts" / "link.py")
    _, rep = run_json(mod, [str(tmp_path / "tool")])
    assert ("scripts/link.py", "symlink") in rules(rep)


def test_skip_rule_and_golden_markdown(tmp_path):
    write_files(tmp_path / "tool", {"scripts/run.py": "import os\nprint(os.getuid())\nx = '/Applications/X.app'\n"})
    rc, out, _ = run_main(mod, [str(tmp_path / "tool"), "--skip-rule", "platform-path"])
    assert rc == 1
    assert out == (
        "# Skill portability check\n\n1 file(s) checked, 1 finding(s).\n\n## tool/scripts/run.py\n\n"
        "- line 2 os-specific-call: os.getuid exists on one platform family only; guard it with os.name or hasattr\n"
    )


def test_this_plugin_passes_its_own_check():
    from conftest import ROOT

    rc, rep = run_json(mod, [str(ROOT / "plugins" / "cc-setup-tooling")])
    assert rc == 0, rep["findings"]
