#!/usr/bin/env python3
"""claude-code-tooling: one command for the claude-code-tooling skill scripts.

    claude-code-tooling <subcommand> [args]       run one skill script with the given arguments
    claude-code-tooling <subcommand> --help       that script's own help
    claude-code-tooling --help                    list the subcommands

Each subcommand runs plugins/claude-code-tooling/skills/<skill>/scripts/<script>.py unchanged, in a child process
with the same Python, stdin, stdout, stderr and exit code. Standard library only. This is the entrypoint of the
container image ghcr.io/basitalisandhu/claude-code-tooling-skills and of the claude-code-tooling-skills Python
package. To add a skill, add one entry to COMMANDS.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

__version__ = "0.1.0"

PROG = "claude-code-tooling"
HERE = Path(__file__).resolve().parent
# In a checkout or the container image the skills sit at <root>/plugins/claude-code-tooling/skills; in the installed
# Python package they sit next to this file, at claude_code_tooling_skills/skills.
SKILLS = next(
    (p for p in (HERE.parent / "plugins" / "claude-code-tooling" / "skills", HERE / "skills") if p.is_dir()),
    HERE.parent / "plugins" / "claude-code-tooling" / "skills",
)

# subcommand: (skill directory, script, one-line summary)
COMMANDS: dict[str, tuple[str, str, str]] = {
    "inventory": (
        "skill-supply-chain-review",
        "skill_inventory.py",
        "Offline inventory of a third-party skill or plugin folder: scripts, imports, URLs, hooks, MCP servers",
    ),
    "desc-lint": (
        "skill-description-linter",
        "description_lint.py",
        "Lint SKILL.md front matter and fix the description quoting",
    ),
    "trigger-eval": (
        "skill-trigger-eval",
        "trigger_eval.py",
        "Score descriptions against labelled prompts (lexical proxy) and compare two versions",
    ),
    "context-budget": (
        "context-budget-audit",
        "context_budget.py",
        "Estimate the tokens a project loads on every turn, rank them and flag waste",
    ),
    "perm-merge": (
        "permissions-builder",
        "perm_merge.py",
        "Merge allow, ask and deny rules from several sources and diff against the current settings",
    ),
    "hook-scaffold": (
        "hook-author",
        "hook_scaffold.py",
        "Scaffold a cc-hooks hook with fixtures, a test and the settings block from a short spec",
    ),
    "collisions": (
        "skill-collision-check",
        "skill_collisions.py",
        "Find skills that share a name, shadow each other or overlap in description",
    ),
    "portability": (
        "skill-portability-check",
        "portability_check.py",
        "Report what in a skill folder breaks on other hosts or operating systems",
    ),
}


def script_path(name: str) -> Path:
    skill, script, _ = COMMANDS[name]
    return SKILLS / skill / "scripts" / script


def usage() -> str:
    width = max(len(n) for n in COMMANDS)
    lines = [
        f"usage: {PROG} <subcommand> [args]",
        "",
        f"Runs one of the claude-code-tooling skill scripts over files you name (no network). "
        f"Use '{PROG} <subcommand> --help' for its options.",
        "",
        "subcommands:",
    ]
    lines += [f"  {n.ljust(width)}  {h} ({script})" for n, (_, script, h) in COMMANDS.items()]
    lines += ["", "options:", "  -h, --help     show this help and exit", "  --version      show the version and exit"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(usage(), file=sys.stderr)
        return 2
    first, rest = args[0], args[1:]
    if first in ("-h", "--help", "help") and not rest:
        print(usage())
        return 0
    if first == "help":
        first, rest = rest[0], ["--help"]
    if first == "--version":
        print(f"{PROG} {__version__}")
        return 0
    if first not in COMMANDS:
        print(f"{PROG}: unknown subcommand {first!r}\n\n{usage()}", file=sys.stderr)
        return 2
    return subprocess.call([sys.executable, str(script_path(first)), *rest])


if __name__ == "__main__":
    sys.exit(main())
