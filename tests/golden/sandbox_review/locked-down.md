# Sandbox configuration review

Platform: linux. Scopes read: user (not given), project `.claude/settings.json`, local `.claude/settings.local.json` (not present), managed `managed.json`.

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
| `sandbox.network.allowAllUnixSockets` | not set | - |
| `sandbox.network.allowLocalBinding` | not set | - |
| `sandbox.enableWeakerNestedSandbox` | not set | - |
| `sandbox.enableWeakerNetworkIsolation` | not set | - |
| `sandbox.allowAppleEvents` | not set | - |
| `sandbox.filesystem.allowManagedReadPathsOnly` | not set | - |

### sandbox.network.allowedDomains

- `registry.npmjs.org` (managed)
- `api.github.com` (managed)

## Domains

### Allowed (2 applied)

- `registry.npmjs.org` (managed, allowedDomains)
- `api.github.com` (managed, allowedDomains)

### Denied (0)

None.

## Findings

None.

## Verify enforcement

Printed, not run. Ask Claude to run each line as a sandboxed Bash command in a session (a line typed at the `!` prompt usually runs outside the sandbox), and decline any offer to retry outside the sandbox.

```bash
touch ~/sandbox-probe  # fails (Operation not permitted or Read-only file system)
curl --noproxy '*' https://example.com  # fails with Could not resolve host
curl -sS -o /dev/null -w "%{http_code}" https://registry.npmjs.org  # connects (any HTTP status from the server, not a proxy 403)
curl -sS -o /dev/null -w "%{http_code}" https://api.github.com  # connects (any HTTP status from the server, not a proxy 403)
curl -sS -o /dev/null -w "%{http_code}" https://example.com  # refused: a 403 from the sandbox proxy or a network prompt (decline it)
```
