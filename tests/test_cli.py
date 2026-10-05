"""Tests for scripts/cli.py, the claude-code-tooling dispatcher used as the container and package entrypoint."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "cli.py"


def run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, timeout=60, cwd=cwd)


def load_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location("claude_code_tooling_cli", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_help_lists_every_subcommand():
    cli = load_cli()
    result = run("--help")
    assert result.returncode == 0
    assert result.stdout.startswith("usage: claude-code-tooling <subcommand>")
    for name, (_, script, _) in cli.COMMANDS.items():
        assert f"  {name} " in result.stdout
        assert script in result.stdout


def test_every_subcommand_points_at_an_existing_script_and_answers_help():
    cli = load_cli()
    for name, (_, script, _) in cli.COMMANDS.items():
        assert cli.script_path(name).is_file(), name
        result = run(name, "--help")
        assert result.returncode == 0, (name, result.stderr)
        assert result.stdout.startswith(f"usage: {script}"), name


def test_every_skill_script_has_a_subcommand():
    cli = load_cli()
    covered = {cli.script_path(n).resolve() for n in cli.COMMANDS}
    scripts = {p.resolve() for p in cli.SKILLS.glob("*/scripts/[a-z]*.py")}
    assert scripts == covered


def test_help_subcommand_shows_the_script_help():
    result = run("help", "portability")
    assert result.returncode == 0
    assert "portability_check.py" in result.stdout


def test_unknown_subcommand_and_no_arguments_exit_2():
    result = run("no-such-command")
    assert result.returncode == 2
    assert "unknown subcommand" in result.stderr
    assert run().returncode == 2


def test_exit_code_and_arguments_pass_through(tmp_path):
    result = run("desc-lint", "--definitely-not-an-option")
    assert result.returncode == 2
    assert "usage: " in result.stderr
    skill = tmp_path / "demo"
    (skill / "scripts").mkdir(parents=True)
    (skill / "scripts" / "show.py").write_text('print(open("notes.txt").read())\n', encoding="utf-8", newline="\n")
    result = run("portability", str(skill), "--json")
    assert result.returncode == 1
    assert json.loads(result.stdout)["findings"][0]["rule"] == "open-no-encoding"


def test_version_matches_every_version_field():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    expected = re.search(r'^version = "([^"]+)"', text, re.MULTILINE).group(1)
    plugin = json.loads(
        (ROOT / "plugins" / "cc-setup-tooling" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert plugin["version"] == expected
    assert market["metadata"]["version"] == expected
    assert all(p["version"] == expected for p in market["plugins"])
    result = run("--version")
    assert result.returncode == 0
    assert result.stdout.strip() == f"claude-code-tooling {expected}"


def test_cli_is_executable_with_a_shebang():
    assert CLI.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3")
    if os.name == "posix":
        assert os.access(CLI, os.X_OK)


def test_pyproject_packages_every_skill_scripts_folder():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for skill in sorted(p.name for p in (ROOT / "plugins" / "cc-setup-tooling" / "skills").iterdir() if p.is_dir()):
        assert f'"plugins/cc-setup-tooling/skills/{skill}/scripts" = ' in text, skill


def test_package_layout_finds_skills_next_to_the_module(tmp_path):
    """The wheel puts cli.py and skills/ side by side in claude_code_tooling_skills/; the dispatcher must find them."""
    pkg = tmp_path / "claude_code_tooling_skills"
    pkg.mkdir()
    shutil.copy(CLI, pkg / "cli.py")
    shutil.copytree(ROOT / "plugins" / "cc-setup-tooling" / "skills", pkg / "skills")
    result = subprocess.run(
        [sys.executable, str(pkg / "cli.py"), "portability", "--help"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=tmp_path,
    )
    assert result.returncode == 0 and result.stdout.startswith("usage: portability_check.py")
