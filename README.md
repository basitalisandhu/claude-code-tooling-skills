# Claude Code skills for keeping your Claude Code setup safe and tidy: review third-party skills, lint and evaluate your own, audit context budget, build least-privilege permissions, author hooks, find collisions and portability problems

**Eight skills, each with an offline, standard-library Python script and tests: skill-supply-chain-review, skill-description-linter, skill-trigger-eval, context-budget-audit, permissions-builder, hook-author, skill-collision-check and skill-portability-check.**

claude-code-tooling-skills is a Claude Code plugin for the upkeep of Claude Code itself. A setup grows by accretion: skills and plugins installed from other people's repositories, descriptions written once and never measured, memory files and MCP servers that fill the context before the first word, permission rules added one "always allow" at a time, hooks copied from examples, two skills with the same name, a script that works on one laptop only. Each skill here turns one of those into a check with a script that reads local files, applies stated rules, and reports what it found with the file and line, leaving the decision to you.

**Who it is for:** people who write or maintain Claude Code skills and plugins, teams that share a `.claude/` folder in a repository, and anyone about to install a skill or plugin they did not write.

**Why:** skill and plugin supply chains are now an attack path, descriptions decide whether a skill is ever used, and the context window is shared by everything installed. The author already maintains command-line tools for parts of this (skill-scan-gate, cc-plugin-lock, claude-perm-sim, claude-mcp-allow, cc-hooks, mcp-tools-lint); these skills tell Claude when and how to run them, and add the offline checks they do not cover.

```text
/plugin marketplace add basitalisandhu/claude-code-tooling-skills
/plugin install cc-setup-tooling@claude-code-tooling-skills
```

Quickstart: open Claude Code in a folder of skills and ask "will this skill work on Windows?" or "why is my context so full?". Or run a script directly from a clone of this repository:

```bash
python3 scripts/cli.py portability path/to/my-skill
python3 scripts/cli.py desc-lint path/to/skills --diff
python3 scripts/cli.py context-budget . --home ~
```

Questions, bugs and ideas: open an issue on this repository. Security reports: see [SECURITY.md](SECURITY.md).

## Install

1. **This marketplace** (above): adds the plugin, named `cc-setup-tooling` because Claude Code reserves plugin names that start with `claude-`, with its skills and keeps the `${CLAUDE_PLUGIN_ROOT}` script paths working.
2. **Through the claude-skills aggregator**, which collects every pack the author maintains in one marketplace: `/plugin marketplace add basitalisandhu/claude-skills`, then `/plugin install cc-setup-tooling@claude-skills`. The aggregator copies packs on its own sync schedule, so check its catalog for this plugin before relying on that route; its `install.py` can also copy skills into `~/.claude/skills` without the plugin system.
3. **Without Claude Code**: run the scripts from a clone (`python3 scripts/cli.py <subcommand>`), build the Python package with `pip install .` (it installs the `claude-code-tooling` command; it is not on PyPI), or use the container image `ghcr.io/basitalisandhu/claude-code-tooling-skills`, which `publish-github-packages.yml` builds for linux/amd64 and linux/arm64 when a version tag is pushed, signed with cosign (keyless), with a build provenance attestation and an SPDX SBOM on the GitHub Release:

   ```bash
   docker run --rm -v "$PWD:/work:ro" ghcr.io/basitalisandhu/claude-code-tooling-skills:0.1.0 portability /work/skills
   ```

After a copy install, each SKILL.md says where its script is relative to the skill folder.

| Subcommand | Script (skill) |
|---|---|
| `inventory` | `skill_inventory.py` (skill-supply-chain-review) |
| `desc-lint` | `description_lint.py` (skill-description-linter) |
| `trigger-eval` | `trigger_eval.py` (skill-trigger-eval) |
| `context-budget` | `context_budget.py` (context-budget-audit) |
| `perm-merge` | `perm_merge.py` (permissions-builder) |
| `hook-scaffold` | `hook_scaffold.py` (hook-author) |
| `collisions` | `skill_collisions.py` (skill-collision-check) |
| `portability` | `portability_check.py` (skill-portability-check) |

## When to use this

- You are about to install a skill or plugin from someone else's repository, or a plugin you locked has changed. `skill-supply-chain-review`
- A skill you wrote is not picked when it should be, or a strict YAML parser rejects its front matter. `skill-description-linter`
- You rewrote a description and want to know whether it now triggers on more of the right requests and fewer of the wrong ones. `skill-trigger-eval`
- Sessions compact early, or you are about to add another MCP server or skill pack. `context-budget-audit`
- You keep approving the same prompts, or `/permissions` shows a wildcard nobody remembers adding. `permissions-builder`
- A team rule ("never read .env", "summarise before stopping") should run every time, not depend on memory. `hook-author`
- The wrong skill ran, or a new plugin arrived with a skill name you already use. `skill-collision-check`
- A skill works on your Mac and fails for a colleague on Windows or in Linux CI. `skill-portability-check`

## Skills

| Skill | Triggers on | Script | Drives |
|---|---|---|---|
| `skill-supply-chain-review` | "is this skill safe to install?" | `skill_inventory.py` | skill-scan-gate, cc-plugin-lock |
| `skill-description-linter` | "why does my skill not trigger?" | `description_lint.py` | none |
| `skill-trigger-eval` | "will this description trigger?" | `trigger_eval.py` | none |
| `context-budget-audit` | "why is my context so full?" | `context_budget.py` | mcp-tools-lint input files |
| `permissions-builder` | "set up permissions for this repo" | `perm_merge.py` | claude-mcp-allow, claude-perm-sim |
| `hook-author` | "add a hook that blocks this command" | `hook_scaffold.py` | cc-hooks |
| `skill-collision-check` | "why did the wrong skill run?" | `skill_collisions.py` | none |
| `skill-portability-check` | "will this skill work on Windows?" | `portability_check.py` | none |

### skill-supply-chain-review

| | |
|---|---|
| Reads | a cloned skill, plugin or marketplace folder |
| Does | runs `skill-scan-gate scan` and `cc-plugin-lock scan`, lists every file with its SHA-256, each script's imports and network, process, dynamic-code and environment use, URLs and domains, shell patterns, credential-store paths, hidden Unicode, hooks, MCP servers, permission rules, symlinks and binaries; locks the reviewed version with `cc-plugin-lock lock` |
| Produces | a one-page verdict: install, install with changes, or do not install, each reason tied to a file and line |

### skill-description-linter

| | |
|---|---|
| Reads | SKILL.md files or folders of them |
| Does | checks double quoting, length (600 by default), verb start, a quoted trigger phrase, "Use when", "Not for", name equal to folder, strict-YAML safety and a `## Limits` section; `--fix` rewrites quoting in place, `--diff` previews it |
| Produces | a per-skill table with listing cost (characters and tokens estimated as characters / 4) and findings with line numbers |

### skill-trigger-eval

| | |
|---|---|
| Reads | a YAML or JSON prompt set of should-trigger and should-not-trigger prompts per skill, and the descriptions |
| Does | scores each prompt with coverage, bigram, quoted-phrase and "Not for" components (formula in the skill), reports precision and recall, compares two versions, and with `--cross` counts sibling skills' prompts as negatives |
| Produces | a precision and recall table and every misjudged prompt with its score parts; a lexical proxy, not the host's choice |

### context-budget-audit

| | |
|---|---|
| Reads | the project, optionally `~/.claude`, and saved MCP `tools/list` results |
| Does | adds up memory files and `@` imports, rules without `paths:`, skill listing entries (capped at 1,536 characters), and MCP tool names, descriptions and schemas; lists on-demand, conditional and not-loaded items separately |
| Produces | totals by category, the largest items, and duplicate, stale-path, stale-date, missing-import, truncated-description, large-item and over-budget findings |

### permissions-builder

| | |
|---|---|
| Reads | settings files, the block `claude-mcp-allow` prints, and text files of `deny`, `ask` and `allow` rules |
| Does | merges and de-duplicates, keeps the stricter list on a conflict, flags broad allows and malformed rules, orders deny before ask before allow, diffs against the current file; the skill then tests the result with `claude-perm-sim explain`, `bypass` and `lint` |
| Produces | a report, or with `--emit settings` the whole settings file with the merged permissions and every other key kept |

### hook-author

| | |
|---|---|
| Reads | a short spec: name, event, matcher, action (block, warn, allow or modify), pattern, message and two examples |
| Does | checks the action is valid for the event, that the pattern separates the examples and that the message references no environment variables, then writes the hook in the cc-hooks pattern |
| Produces | the hook, a pytest file, `match.json` and `nomatch.json` fixtures for `cc-hooks test`, and the settings block in exec form |

### skill-collision-check

| | |
|---|---|
| Reads | managed, personal and project skill folders, `.claude/commands`, installed plugins (from `installed_plugins.json` or the cache) and any other folder you name |
| Does | applies the documented precedence (managed over personal over project; plugin skills namespaced; a skill over a command of the same name) and compares descriptions by word cosine |
| Produces | shadowed, command-vs-skill, plugin-duplicate, duplicate-in-folder, builtin-name and description-overlap findings, each naming what wins |

### skill-portability-check

| | |
|---|---|
| Reads | every file in a skill or plugin folder |
| Does | checks front matter for strict YAML, home and platform-only paths, `${CLAUDE_PLUGIN_ROOT}` without a copy-install path, GNU-only or BSD-only shell, bashisms under `/bin/sh`, hard-coded shebangs, Python text I/O without `encoding=`, POSIX-only or Windows-only calls outside a platform check, backslash paths, CRLF, symlinks and case collisions |
| Produces | findings per file with the line and a fix hint; `--skip-rule` for skills meant for one platform |

This repository's own plugin passes its description linter and portability check; CI runs both.

## Security posture

- **Local, offline scripts.** The skill scripts read the files you name. They import no network or subprocess module (the repository validator checks this) and write only to standard output, the `--out` path you give, or, for `description_lint.py --fix`, the SKILL.md files you pointed it at.
- **Third-party content is data.** Every SKILL.md tells Claude to treat input files as untrusted data, never as instructions; this matters most for `skill-supply-chain-review`, whose input is code you have not reviewed yet.
- **Separate tools run separately.** The skills tell Claude how to run skill-scan-gate, cc-plugin-lock, cc-hooks, claude-perm-sim and claude-mcp-allow; nothing in this repository installs or calls them. `claude-mcp-allow` starts the MCP servers configured for a project, which the permissions-builder skill says before it is run.
- **Synthetic tests.** Tests build their inputs at run time with made-up names; risky shell text in tests is assembled from parts.

## What is inside

```text
.claude-plugin/marketplace.json                       marketplace manifest
plugins/cc-setup-tooling/
├── .claude-plugin/plugin.json                        plugin manifest
├── README.md                                         the plugin's skill table
└── skills/<name>/
    ├── SKILL.md                                      when to use it, inputs, steps, script, output, limits, related skills
    └── scripts/<script>.py                           standard library only, --help, --json, --out, exit 0, 1 or 2
                 _skillmd.py                          shared front matter reader (identical copies, checked by a test)
scripts/cli.py                                        the claude-code-tooling dispatcher (container and package entrypoint)
scripts/validate_plugin.py                            structure, front matter, scripts, READMEs, house style
tests/                                                pytest suite, offline; inputs are built in each test
```

## Development

```bash
python3 -m pytest -q
ruff format --check . && ruff check .
python3 scripts/validate_plugin.py
claude plugin validate --strict . && claude plugin validate --strict plugins/cc-setup-tooling
```

CI runs the tests on Linux, macOS and Windows with Python 3.10 to 3.13, builds the container image, and runs `claude plugin validate --strict`. See [CONTRIBUTING.md](CONTRIBUTING.md) for the ground rules and [docs/good-first-issues.md](docs/good-first-issues.md) for a place to start.

## Frequently asked questions

**Does skill-supply-chain-review prove a skill is safe?**
No. It combines two rule-based scanners with an inventory a person reads, and ends in a verdict a person signs. Nothing is executed, so behaviour that depends on downloaded code or the environment is not seen.

**Do I need skill-scan-gate, cc-plugin-lock, cc-hooks, claude-perm-sim or claude-mcp-allow installed?**
Only for the steps that use them. Every bundled script runs on Python 3.10 with nothing else installed; the skills say what to do when a tool is missing.

**Is skill-trigger-eval how Claude Code chooses skills?**
No. The host reads descriptions with a language model. The script measures word and phrase overlap, which is useful for comparing two wordings against the same prompts and spotting plain misses, and it says so in its output.

**Are the token numbers exact?**
No. context-budget-audit and skill-description-linter estimate tokens as characters / 4 and say so.

**Will permissions-builder edit my settings.json?**
No. It prints a report or a proposed settings file; copying it into place is your step, after testing it with claude-perm-sim.

**Why does skill-portability-check flag ~/Library in my macOS skill?**
Because the path exists on one platform only. For a skill that is meant for macOS, pass `--skip-rule platform-path` and say so in the skill's Limits.

**Can I run these in CI?**
Yes. Each script exits 1 when something needs a person and 2 on bad input, so `desc-lint`, `portability` and `collisions` work as CI gates.

## Related repositories

| Repository | What it is |
|---|---|
| [skill-scan-gate](https://github.com/basitalisandhu/skill-scan-gate) | CI gate that scans skill and plugin repositories for unsafe instructions, hooks and MCP servers, with SARIF output |
| [cc-plugin-lock](https://github.com/basitalisandhu/cc-plugin-lock) | Lock file that pins installed plugins and skills to content hashes, verifies them before a session and scans a folder before install |
| [claude-perm-sim](https://github.com/basitalisandhu/claude-perm-sim) | Permission rule simulator: which rule decides a call, and where an allow rule admits more than it names |
| [claude-mcp-allow](https://github.com/basitalisandhu/claude-mcp-allow) | Least-privilege permission rules for MCP tools from their annotations, with drift checks |
| [cc-hooks](https://github.com/basitalisandhu/cc-hooks) | Typed Python SDK and offline test runner for Claude Code hooks |
| [mcp-tools-lint](https://github.com/basitalisandhu/mcp-tools-lint) | Lint MCP tool schemas and annotations from a server or a saved tools/list result |
| [claude-skills](https://github.com/basitalisandhu/claude-skills) | Every skill pack the author maintains, in one marketplace |

More from the author: [basitalisandhu.github.io](https://basitalisandhu.github.io/).

## Licence

MIT. See [LICENSE](LICENSE).
