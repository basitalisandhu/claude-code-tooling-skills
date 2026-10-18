# Sandbox configuration review

Platform: linux. Scopes read: user (not given), project `.claude/settings.json`, local `.claude/settings.local.json`, managed `managed.json`.

Admin-required sandbox: yes (managed allowUnsandboxedCommands is false).

Rules from https://code.claude.com/docs/en/sandboxing.

## Effective settings

| Key | Value | Source |
|---|---|---|
| `sandbox.enabled` | true | managed |
| `sandbox.failIfUnavailable` | true | managed |
| `sandbox.allowUnsandboxedCommands` | false | managed |
| `sandbox.autoAllowBashIfSandboxed` | true (default) | default |
| `sandbox.filesystem.disabled` | false (default) | default |
| `sandbox.network.strictAllowlist` | not set | - |
| `sandbox.network.allowManagedDomainsOnly` | not set | - |
| `sandbox.network.allowAllUnixSockets` | not set | - (local true ignored: admin-required sandbox ignores a repository true) |
| `sandbox.network.allowLocalBinding` | not set | - |
| `sandbox.enableWeakerNestedSandbox` | not set | - |
| `sandbox.enableWeakerNetworkIsolation` | not set | - |
| `sandbox.allowAppleEvents` | not set | - |
| `sandbox.filesystem.allowManagedReadPathsOnly` | not set | - |

### sandbox.excludedCommands

- `docker *` (project) (ignored: admin-required sandbox (managed allowUnsandboxedCommands is false) ignores repository entries)
- `gh *` (managed)

### sandbox.filesystem.denyRead

- `.env` (managed)

### sandbox.network.allowedDomains

- `*.com` (project) (ignored: admin-required sandbox (managed allowUnsandboxedCommands is false) ignores repository entries)
- `github.com` (managed)

### sandbox.network.deniedDomains

- `gist.github.com` (managed)

## Domains

### Allowed (1 applied)

- `*.com` (project, allowedDomains) (ignored: admin-required sandbox (managed allowUnsandboxedCommands is false) ignores repository entries)
- `github.com` (managed, allowedDomains)
- `gist.github.com` (project, WebFetch(domain:) allow rule) (ignored: admin-required sandbox (managed allowUnsandboxedCommands is false) ignores repository entries)

### Denied (1)

- `gist.github.com` (managed, deniedDomains)

## Findings

- low domain-wildcard-broad (project) `*.com (allowedDomains)`: allows every host under the top-level domain .com (ignored now: admin-required sandbox (managed allowUnsandboxedCommands is false) ignores repository entries)
- low excluded-command-broad (project) `docker *`: runs a container tool (docker) outside the sandbox with your full access (ignored now: admin-required sandbox (managed allowUnsandboxedCommands is false) ignores repository entries)
- low repo-loosens (project) `allowedDomains: *.com`: set in the committed .claude/settings.json but ignored here: admin-required sandbox (managed allowUnsandboxedCommands is false) ignores repository entries
- low repo-loosens (project) `enabled: false`: set in the committed .claude/settings.json but ignored here: managed settings set this key
- low repo-loosens (project) `excludedCommands: docker *`: set in the committed .claude/settings.json but ignored here: admin-required sandbox (managed allowUnsandboxedCommands is false) ignores repository entries

## Verify enforcement

Printed, not run. Ask Claude to run each line as a sandboxed Bash command in a session (a line typed at the `!` prompt usually runs outside the sandbox), and decline any offer to retry outside the sandbox.

```bash
touch ~/sandbox-probe  # fails (Operation not permitted or Read-only file system)
curl --noproxy '*' https://example.com  # fails with Could not resolve host
curl -sS -o /dev/null -w "%{http_code}" https://github.com  # connects (any HTTP status from the server, not a proxy 403)
curl -sS -o /dev/null -w "%{http_code}" https://example.com  # refused: a 403 from the sandbox proxy or a network prompt (decline it)
curl -sS -o /dev/null -w "%{http_code}" https://gist.github.com  # refused in every permission mode (deniedDomains)
```
