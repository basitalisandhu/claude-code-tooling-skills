# Changelog

All notable changes to this project are documented here. The format follows Keep a Changelog, and the project uses semantic versioning.

## [Unreleased]

## [0.1.0] - 2026-10-05

### Added

- Plugin marketplace `claude-code-tooling-skills` with one plugin, `cc-setup-tooling`, whose skills each have a tested standard-library script that reads local files and never calls the network.
- `skill-supply-chain-review`: a review procedure that runs skill-scan-gate and cc-plugin-lock on a third-party skill or plugin, and `skill_inventory.py`, an offline inventory of files with hashes, script imports and network, process, dynamic-code and environment use, URLs and domains, shell patterns, credential-store paths, hidden Unicode, hooks, MCP servers, permission rules, symlinks and binaries.
- `skill-description-linter`: `description_lint.py` checks double quoting, length, verb start, a quoted trigger phrase, Use when, Not for, name against folder, strict-YAML safety and a Limits section, reports listing cost, and rewrites quoting with `--fix` (preview with `--diff`).
- `skill-trigger-eval`: `trigger_eval.py` scores descriptions against a labelled YAML or JSON prompt set with documented coverage, bigram, phrase and Not-for components, reports precision and recall, compares two versions, and counts sibling prompts as negatives with `--cross`.
- `context-budget-audit`: `context_budget.py` estimates the tokens of memory files and imports, rules, skill listing entries and MCP tool schemas from saved tools/list results, ranks them, lists on-demand items separately, and flags duplicates, stale paths and dates, missing imports, truncated descriptions, large items and an over-budget total.
- `permissions-builder`: a procedure around claude-mcp-allow and claude-perm-sim, and `perm_merge.py`, which merges allow, ask and deny rules from settings files, permission blocks and text lists, resolves conflicts to the stricter list, flags broad and malformed rules, orders deny first and diffs against the current settings.
- `hook-author`: an event and decision table, and `hook_scaffold.py`, which turns a short spec into a cc-hooks hook, a pytest file, cc-hooks fixtures and a settings block, after checking the pattern against two examples.
- `skill-collision-check`: `skill_collisions.py` reads managed, personal, project, plugin and other skill folders and commands, and reports shadowed names, commands hidden by skills, plugin duplicates, duplicate names in one folder, built-in names and overlapping descriptions, naming what wins.
- `skill-portability-check`: `portability_check.py` reports strict-YAML problems, home and platform-only paths, plugin-root paths without a copy-install fallback, non-portable shell and bashisms, hard-coded shebangs, Python text I/O without encoding, platform-only calls, backslash paths, CRLF, symlinks and case collisions, with a fix hint each.
- `scripts/cli.py`: the `claude-code-tooling <subcommand>` dispatcher (`inventory`, `desc-lint`, `trigger-eval`, `context-budget`, `perm-merge`, `hook-scaffold`, `collisions`, `portability`), used by the container image and the Python package.
- `scripts/validate_plugin.py`; a pytest suite whose inputs are built at run time; CI on Python 3.10 to 3.13 on Linux, macOS and Windows, a container build check, `claude plugin validate --strict`, and the plugin's own description lint and portability check.
- `Dockerfile` and `publish-github-packages.yml`: on a `v*` tag, the image `ghcr.io/basitalisandhu/claude-code-tooling-skills` for linux/amd64 and linux/arm64 with an SPDX SBOM, a build provenance attestation and a keyless cosign signature.
- Tasks for new contributors in `docs/good-first-issues.md`.

[Unreleased]: https://github.com/basitalisandhu/claude-code-tooling-skills/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/basitalisandhu/claude-code-tooling-skills/releases/tag/v0.1.0
