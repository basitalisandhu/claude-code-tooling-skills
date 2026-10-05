# Security policy

This repository ships skills and scripts that run inside people's Claude Code sessions over their own files and over skills and plugins they have not reviewed yet: skill folders, plugin folders, settings files, memory and rules files, saved MCP `tools/list` results and hook specs. The skill scripts read the files or folders you point them at and print a report or write it to the path you name; nothing here makes a network call, stores a credential or reports usage anywhere.

## Supported versions

Only the latest release on `main` is supported. Pin a tag if you need stability, and update when a fix is announced in [CHANGELOG.md](CHANGELOG.md).

## Reporting a vulnerability

Please do not open a public issue for a security problem.

1. Use GitHub's private vulnerability reporting on this repository ("Security" tab, "Report a vulnerability").
2. If that is unavailable, open an issue titled "Security contact request" with no details, and the maintainer will reply with a private channel.

Include what you found, how to reproduce it, and what you think the impact is. You will get an acknowledgement within 5 working days and a fix or a mitigation plan within 30 days for confirmed issues.

## What counts

- A skill script that opens a network connection, starts a subprocess, executes or imports code from the folder it inspects, or writes anywhere other than standard output, the `--out` path it was given, or (for `description_lint.py --fix`) the SKILL.md files it was pointed at.
- A way for the content of an inspected folder (a SKILL.md, a script, a settings file) to change what a script computes beyond its documented rules, to hide an item from the inventory, or to make a script read files outside the input it was given.
- A generated hook from `hook_scaffold.py` that can print a secret, or that fails open when its spec says closed.
- Text in any file of this repository that addresses the model rather than the reader.
- A committed file holding real names, real infrastructure details or a secret-shaped string.

Rule mistakes (a pattern the inventory misses, a portability rule that fires wrongly, a precedence the collision check gets wrong) are welcome as ordinary issues or pull requests with a test that shows them.

## What this plugin does and does not do

- No telemetry and no network access in the skill scripts.
- Scripts are standard-library Python, parse what they inspect as text, JSON or a Python syntax tree, and never run it.
- `scripts/cli.py` starts the chosen skill script as a child process with the same Python and passes the arguments unchanged.
- The separate tools the skills mention (skill-scan-gate, cc-plugin-lock, cc-hooks, claude-perm-sim, claude-mcp-allow) are installed and run by the user; `claude-mcp-allow` starts configured MCP servers, which the skill states before running it.
- Skill text tells Claude to treat the content of input files as untrusted data, never as instructions.
