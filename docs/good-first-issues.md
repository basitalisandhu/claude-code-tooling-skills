# Good first issues

Small, well-specified pieces of work for a first contribution. Each is self-contained, comes with the test to add, and needs no account, token or network access: tests build their own inputs. Read [CONTRIBUTING.md](../CONTRIBUTING.md) first: standard library only, `encoding="utf-8"` on every file call, a test for every rule change, made-up names only, plain language without em-dashes.

To claim one, open an issue with the title below (or comment on the existing one) and say you are working on it. Run `python3 -m pytest -q`, `ruff check .` and `python3 scripts/validate_plugin.py` before opening the pull request.

## 1. skill-supply-chain-review: list PowerShell download and execution patterns

**Labels:** good first issue, skill-supply-chain-review, python

**Context.** `skill_inventory.py` lists shell patterns line by line, but its patterns are written for POSIX shells. A `.ps1` script that downloads and runs code is classed as a script and nothing more.

**Acceptance criteria.**
- New shell pattern labels for PowerShell downloads (`Invoke-WebRequest`, `iwr`, `Invoke-RestMethod`, `irm`) and for evaluating strings (`Invoke-Expression`, `iex`), applied to `.ps1` files.
- A test with one `.ps1` file that has each pattern and one that has none. Build the risky text from parts.

## 2. skill-description-linter: flag descriptions that open with the mechanism

**Labels:** good first issue, skill-description-linter, python

**Context.** The house rule puts the user's goal before the mechanism, but the linter does not check it.

**Acceptance criteria.**
- A rule `description-mechanism-first` when "script", "bundled", "Python" or "scanner" appears in the first sentence before any of the words the user would care about, documented in the module docstring and the SKILL.md rule table, reported as advice (it does not change the exit code on its own unless `--strict` is given).
- Tests with one description that starts with "A bundled script ..." and one that starts with the goal.

## 3. context-budget-audit: count command descriptions

**Labels:** good first issue, context-budget-audit, python

**Context.** Files in `.claude/commands/` also have descriptions in the listing, and the audit leaves them out.

**Acceptance criteria.**
- A `commands` category that counts the `description` front matter (or the first line when there is none) of each command file in the project and the home folder, as every turn.
- A test with one command that has a description and one that has none, and an updated SKILL.md "What counts as every turn" paragraph.

## 4. permissions-builder: report allow rules covered by a broader allow

**Labels:** good first issue, permissions-builder, python

**Context.** `Bash(git status)` next to `Bash(git *)` is redundant, but `perm_merge.py` only removes exact duplicates.

**Acceptance criteria.**
- A `covered-allow` finding when a Bash allow rule's literal prefix is matched by another allow rule ending in ` *`, without removing it.
- Tests with one covered rule and one rule that only looks similar (`Bash(git-lfs pull)` next to `Bash(git *)`).

## 5. skill-portability-check: flag `python` without the 3

**Labels:** good first issue, skill-portability-check, python

**Context.** A SKILL.md that runs `python script.py` fails on hosts where only `python3` exists, and the reverse holds on Windows with the `py` launcher.

**Acceptance criteria.**
- A rule `python-command` for a bare `python ` at the start of a command in bash code blocks of SKILL.md, with a hint to use `python3` and to state the interpreter in `compatibility`.
- Tests with `python x.py` flagged and `python3 x.py` and `python3.12 -m venv` not flagged.

## 6. skill-collision-check: read commands from installed plugins

**Labels:** good first issue, skill-collision-check, python

**Context.** Plugins can ship slash commands in `commands/`, and a plugin command can share a name with a standalone skill or another plugin's command.

**Acceptance criteria.**
- Plugin commands are read from each installed plugin's `commands/*.md` and reported under `plugin-duplicate` when another plugin or a standalone skill uses the same name.
- A test with two plugins in a synthetic `installed_plugins.json`, each with a `commands/deploy.md`.
