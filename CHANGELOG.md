# Changelog

All notable changes to this project are documented here. The format follows Keep a Changelog, and the project uses semantic versioning.

## [Unreleased]

## [0.5.0] - 2026-10-26

Three skills that read Claude Code session transcripts (`~/.claude/projects/**/*.jsonl`, subagent transcripts included). The transcript format is not documented: each script reads it defensively, counts unreadable lines and unknown line types and reports them, and exits 2 only when nothing usable was read. They share a small reader, `_transcript.py`, as identical copies checked by a test.

### Added

- `session-usage-ledger`: `usage_ledger.py` merges the assistant lines of one API response by message id and request id (keeping the largest value of each usage field), then adds up calls, uncached input, output, cache read and 5-minute and 1-hour cache write tokens per UTC day, session, model and project, with the cache-hit ratio read / (read + write + uncached input), each session's first-call size and the subagent share. `--compare-weeks` or `--baseline A..B --period C..D` shows which component moved (calls, context per call, cache hits, 5-minute share of writes, first-call size). Findings: `cache-ttl-5m` (with `--expect-ttl 1h`), `low-cache-hit`, `first-call-overhead`, `period-jump`. `--rates` estimates cost from the user's own per-million rates; nothing is priced otherwise. Text, Markdown or JSON; exit 0, 1, 2. 12 tests. Subcommand `usage-ledger`.
- `shell-slip-audit`: `shell_slips.py` pairs every Bash and PowerShell call with its result and classifies failures that come from the shell: zsh `no matches found` on a flag value or a path glob, `=` word expansion, bad pattern, parse error, bad substitution, bash-only builtins, colon modifiers, array subscripts, glob qualifiers, command not found, a heredoc or bash syntax sent to PowerShell, Bash commands on Windows near the 8,186-character limit, and a sandbox that cannot start the shell, with interrupted and timed-out calls counted as stops. It reports slips per 1,000 shell calls, the silent share (result not marked as an error), the repeat rate, a table per pattern and per session with an example and a fix, and `--emit-rule` prints a CLAUDE.md block. `--max-rate`; exit 0, 1, 2. 10 tests. Subcommand `shell-slips`.
- `compaction-loss-check`: `compaction_check.py` reports each `compact_boundary` (trigger, tokens before and after, minutes since the last user message, idle compactions) and checks the summary that follows for the standing rules the user gave, files edited or written, branches and pull requests created, and open `TodoWrite` or task items, each kept, partly kept or missing. It prints a re-state list per compaction, and `--emit-recap` a block to paste back into the session. Exit 1 when a standing rule or an edited file is missing; 0, 2 as usual. 11 tests. Subcommand `compaction-check`.
- Synthetic transcript fixtures in `tests/fixtures/transcripts/`, used by the tests and the README samples. 4 tests for the shared reader.
- CI: the container job runs `usage-ledger`, `shell-slips` and `compaction-check` on the fixtures.

## [0.4.0] - 2026-10-20

### Added

- `unattended-run-preflight`: `unattended_preflight.py` replays the tool calls of a previous run (a Claude Code session log, where a refused call is marked) or a JSON list of calls against the deny, ask and allow rules of the managed, `--settings`, local, project and user scopes, following the permissions page: compound commands split, the fixed wrappers stripped, allow rules not matched past a leading assignment, output redirects checked as edits, built-in read-only commands and working-directory reads need no approval, `acceptEdits`, `dontAsk` and `bypassPermissions` modes. It lists the calls that would stall an unattended run (or be refused in `dontAsk`), the calls a deny rule blocks, the narrowest allow rule for each, and a separate list for rules that change, publish, comment or run a shell or interpreter. `--emit-rules` prints the `permissions` block. Exit 0, 1 when any call needs approval or is denied, 2 bad input. 18 tests. Subcommand `unattended-preflight`.
- `subagent-tool-scope-review`: `subagent_scope.py` reads project, user and plugin agent files and MCP config files and reports what each subagent can reach (built-in tools, MCP servers, write, shell, web) with findings: `inherits-all-tools`, `lookalike-field` (`allowed-tools` and similar are ignored in agent files), `read-only-job-with-write-tools`, `bypass-mode`, `loose-mode-for-reader`, `server-wide-mcp-grant`, `inline-mcp-server`, `specifier-in-tools`, `disallowed-specifier`, fields a plugin agent ignores and malformed front matter, with a narrower `tools` line for readers. `--fail-on`; exit 0, 1, 2. 14 tests. Subcommand `subagent-scope`.
- CI: the container job runs `subagent-scope` on a sample agent.

## [0.3.0] - 2026-10-18

Every skill was checked against the current Claude Code documentation (settings reference, sandboxing, permissions, hooks, plugins reference and skills pages, read 2026-10-18). What had gone stale is fixed below, each with a test.

### Added

- `permissions-builder`: `allow-glob-ignored` (an allow rule such as `*`, `B*` or `mcp__*` with no literal `mcp__<server>__` prefix approves nothing, so it is dropped; it used to be reported as broad or as malformed), `wildcard-before-subcommand` (`Bash(* --version)`, `Bash(git * main)`), `colon-star-literal` (`:*` before the end of a pattern, where the colon is literal). Deny and ask rules may now glob the tool name (`*`, `mcp__*`), as the permissions page allows. `PowerShell` and `PowerShell(*)` count as broad allows.
- `sandbox-config-review`: `network.allowMachLookup` (`mach-lookup-all` when it holds `"*"`, ignored from the repository when the sandbox is admin-required), `filesystem.allowManagedReadPathsOnly` (only managed `allowRead` entries count), the managed read lock (a repository `allowRead` cannot re-open a path managed or user settings deny), `managed-only-key-ignored` for `allowManagedDomainsOnly`, `allowManagedReadPathsOnly`, `bwrapPath` and `socatPath` set outside managed settings, and type checks for `ignoreViolations`, `bwrapPath` and `socatPath`.
- README: a quick start that runs as written from a clone, with its real output.

### Fixed

- `skill-portability-check`: the copy-install note this author's other packs adopted ("If this skill was copied ... without the plugin system ... Replace `${CLAUDE_PLUGIN_ROOT}/skills/x` with the path to this skill's folder") was still reported as `plugin-root-no-fallback`, because it names the variable; 8 false findings on ways-of-working-skills and repo-engineering-skills are gone. The hint now also offers `${CLAUDE_SKILL_DIR}/scripts/<file>`, which Claude Code resolves for personal, project and plugin skills.
- `context-budget-audit`: a skill with `disable-model-invocation: true` was counted in the every-turn total; its description stays out of context, so it is now listed as not loaded.
- `sandbox-config-review`: the documented command `--user ~/.claude/settings.json` exited 2 on a fresh install with no user settings file; a missing `--user` file is now an empty user scope with a note. A missing `--managed` file still exits 2.
- `perm_merge.py`: a text source that is not UTF-8 exits 2 instead of a traceback.
- `hook-author`: the Stop row of the action table says that a warn keeps Claude working, with the loop guard.

## [0.2.0] - 2026-10-16

### Added

- `sandbox-config-review`: `sandbox_review.py` reads a project's `.claude/settings.json` and `.claude/settings.local.json` and the user and managed settings files you name, merges the `sandbox` keys and the related permission rules the way the official sandboxing page states (managed Boolean keys win, arrays merge, keys a repository cannot set, admin-required and strict-allowlist locks), and reports each effective value with its source scope, the allowed and denied domains with `WebFetch(domain:...)` rules marked, and findings: `sandbox-off`, `windows-native-unsandboxed`, `fail-open`, `escape-hatch-open`, `excluded-command-broad`, `domain-wildcard-broad` (with a documented default list of publishable-host suffixes), `allow-deny-conflict`, `credentials-readable`, `filesystem-disabled`, `unix-sockets-all`, `weaker-isolation`, `proxy-port-set`, `repo-loosens` and `strict-allowlist-ignored-scope`. It prints, never runs, curl checks to confirm enforcement in a session. Markdown or JSON, `--fail-on high|medium|low`; exit 0, 1 findings, 2 bad input. 20 tests with golden outputs for four synthetic projects; `claude-code-tooling sandbox-review` subcommand and a container CI sample.
- `python-command` portability rule flags bare `python` commands in shell code blocks and recommends `python3` with the interpreter stated in compatibility notes.

## [0.1.1] - 2026-10-05

### Fixed

- `skill-description-linter`: `description-verb-start` no longer fires on descriptions whose first word is hyphenated (`Stress-test`, `Re-run`) or followed by punctuation (`Build,`, `Review:`) (#7).

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

[Unreleased]: https://github.com/basitalisandhu/claude-code-tooling-skills/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/basitalisandhu/claude-code-tooling-skills/releases/tag/v0.2.0
[0.1.1]: https://github.com/basitalisandhu/claude-code-tooling-skills/releases/tag/v0.1.1
[0.1.0]: https://github.com/basitalisandhu/claude-code-tooling-skills/releases/tag/v0.1.0
