# Sandbox configuration review

Platform: linux. Scopes read: user `user.json`, project `.claude/settings.json`, local `.claude/settings.local.json` (not present), managed (not given).

Admin-required sandbox: no.

Rules from https://code.claude.com/docs/en/sandboxing.

## Effective settings

| Key | Value | Source |
|---|---|---|
| `sandbox.enabled` | true | user |
| `sandbox.failIfUnavailable` | true | user |
| `sandbox.allowUnsandboxedCommands` | false | user (project true ignored: a user false holds against a project true) |
| `sandbox.autoAllowBashIfSandboxed` | true (default) | default |
| `sandbox.filesystem.disabled` | false (default) | default |
| `sandbox.network.strictAllowlist` | not set | - (project true ignored: not honoured from project or local settings) |
| `sandbox.network.allowManagedDomainsOnly` | not set | - |
| `sandbox.network.allowAllUnixSockets` | not set | - |
| `sandbox.network.allowLocalBinding` | not set | - |
| `sandbox.enableWeakerNestedSandbox` | not set | - |
| `sandbox.enableWeakerNetworkIsolation` | not set | - |
| `sandbox.allowAppleEvents` | not set | - |
| `sandbox.filesystem.allowManagedReadPathsOnly` | not set | - |

### sandbox.excludedCommands

- `docker compose *` (project)

### sandbox.filesystem.allowWrite

- `~/.local/bin` (project)

### sandbox.filesystem.denyRead

- `~/.ssh` (project)
- `~/.aws` (project)
- `.env` (project)

### sandbox.network.allowedDomains

- `*.githubusercontent.com` (project)
- `pypi.org` (project)

### sandbox.network.httpProxyPort

- `8080` (project)

## Domains

### Allowed (2 applied)

- `*.githubusercontent.com` (project, allowedDomains)
- `pypi.org` (project, allowedDomains)

### Denied (0)

None.

## Findings

- high repo-loosens (project) `allowedDomains: *.githubusercontent.com`: set in the committed .claude/settings.json, so anyone who clones the repository gets it
- high repo-loosens (project) `excludedCommands: docker compose *`: set in the committed .claude/settings.json, so anyone who clones the repository gets it
- high repo-loosens (project) `filesystem.allowWrite: ~/.local/bin`: set in the committed .claude/settings.json, so anyone who clones the repository gets it
- high repo-loosens (project) `network.httpProxyPort: 8080`: set in the committed .claude/settings.json, so anyone who clones the repository gets it
- medium domain-wildcard-broad (project) `*.githubusercontent.com (allowedDomains)`: covers hosts anyone can publish to (githubusercontent.com, in the default list)
- medium excluded-command-broad (project) `docker compose *`: runs a container tool (docker) outside the sandbox with your full access
- medium proxy-port-set (project) `sandbox.network.httpProxyPort = 8080`: your own proxy now filters this traffic; allowedDomains, deniedDomains, strictAllowlist and approval prompts stop applying to it
- medium strict-allowlist-ignored-scope (project) `sandbox.network.strictAllowlist`: has no effect in project or local settings; set it in user or managed settings
- low repo-loosens (project) `allowUnsandboxedCommands: true`: set in the committed .claude/settings.json but ignored here: a user false holds against a project true

## Verify enforcement

Printed, not run. Ask Claude to run each line as a sandboxed Bash command in a session (a line typed at the `!` prompt usually runs outside the sandbox), and decline any offer to retry outside the sandbox.

```bash
touch ~/sandbox-probe  # fails (Operation not permitted or Read-only file system)
curl --noproxy '*' https://example.com  # fails with Could not resolve host
curl -sS -o /dev/null -w "%{http_code}" https://<a host under githubusercontent.com>  # connects (any HTTP status from the server, not a proxy 403); but a proxy port applies, so your own proxy decides
curl -sS -o /dev/null -w "%{http_code}" https://pypi.org  # connects (any HTTP status from the server, not a proxy 403); but a proxy port applies, so your own proxy decides
curl -sS -o /dev/null -w "%{http_code}" https://example.com  # refused: a 403 from the sandbox proxy or a network prompt (decline it); but a proxy port applies, so your own proxy decides
```
