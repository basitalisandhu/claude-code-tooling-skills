"""Shared helpers for the script tests.

Every skill script lives at plugins/cc-setup-tooling/skills/<skill>/scripts/<name>.py and is a standalone program,
not a package. Tests load one by path with load_script() and call its main(argv), capturing stdout and stderr.
There are no fixture files on disk: each test builds its synthetic input in pytest's tmp_path with write_files(),
using made-up names and example values only. Nothing here touches the network.

Tests marked posix_only need POSIX file modes or symbolic links and are skipped on Windows; everything else runs on
Linux, macOS and Windows.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import textwrap
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "plugins" / "cc-setup-tooling" / "skills"


def pytest_collection_modifyitems(config, items):
    if os.name != "nt":
        return
    skip = pytest.mark.skip(reason="needs POSIX file modes or symbolic links")
    for item in items:
        if "posix_only" in item.keywords:
            item.add_marker(skip)


def script_path(skill: str, name: str) -> Path:
    return SKILLS / skill / "scripts" / name


def load_script(skill: str, name: str):
    """Import a skill script by path under a unique module name."""
    path = script_path(skill, name)
    module_name = f"skill_{skill}_{path.stem}".replace("-", "_")
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def run_main(module, argv: list[str]) -> tuple[int, str, str]:
    """Run module.main(argv) and return (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            rc = module.main(argv)
        except SystemExit as exc:  # argparse --help and usage errors
            rc = int(exc.code or 0)
    return rc, out.getvalue(), err.getvalue()


def run_json(module, argv: list[str]) -> tuple[int, dict]:
    rc, out, err = run_main(module, [*argv, "--json"])
    try:
        return rc, json.loads(out)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"not JSON (rc={rc}): {out!r} stderr={err!r}") from exc


def write_files(folder: Path, files: dict[str, str]) -> Path:
    """Write {relative path: text} under folder (text is dedented, LF endings) and return the folder."""
    for rel, text in files.items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8", newline="\n")
    return folder


def skill_md(name: str, description: str, body: str = "## Limits\n\n- None known.\n", **extra: str) -> str:
    """A SKILL.md with a double-quoted description (inner quotes escaped) and the given body."""
    desc = description.replace("\\", "\\\\").replace('"', '\\"')
    lines = ["---", f"name: {name}", f'description: "{desc}"', "license: MIT"]
    lines += [f"{k.replace('_', '-')}: {v}" for k, v in extra.items()]
    return "\n".join(lines) + "\n---\n\n# Title\n\n" + body
