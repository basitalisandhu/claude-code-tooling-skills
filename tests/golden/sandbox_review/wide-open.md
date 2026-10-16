# Sandbox configuration review

Platform: linux. Scopes read: user `user.json`, project `.claude/settings.json`, local `.claude/settings.local.json`, managed (not given).

Admin-required sandbox: no.

Rules from https://code.claude.com/docs/en/sandboxing.

## Effective settings

| Key | Value | Source |
|---|---|---|
| `sandbox.enabled` | true | project |
| `sandbox.failIfUnavailable` | false (default) | default |
| `sandbox.allowUnsandboxedCommands` | true (default) | default |
| `sandbox.autoAllowBashIfSandboxed` | true (default) | default |
| `sandbox.filesystem.disabled` | true | user |
| `sandbox.network.strictAllowlist` | not set | - (local true ignored: not honoured from project or local settings) |
| `sandbox.network.allowManagedDomainsOnly` | not set | - |
| `sandbox.network.allowAllUnixSockets` | true | user |
| `sandbox.network.allowLocalBinding` | not set | - |
| `sandbox.enableWeakerNestedSandbox` | not set | - |
| `sandbox.enableWeakerNetworkIsolation` | not set | - |
| `sandbox.allowAppleEvents` | not set | - |

### sandbox.excludedCommands

- `bash *` (project)
- `curl *` (project)
- `python scripts/load_data.py *` (project)

### sandbox.network.allowedDomains

- `*` (project)
- `*.com` (project)
- `*.blob.core.windows.net` (project)
- `registry.npmjs.org` (project)

## Domains

### Allowed (5 applied)

- `*` (project, allowedDomains)
- `*.com` (project, allowedDomains)
- `*.blob.core.windows.net` (project, allowedDomains)
- `registry.npmjs.org` (project, allowedDomains)
- `*.ngrok.io` (local, WebFetch(domain:) allow rule)
- `docs.example.*` (local, WebFetch(domain:) allow rule) (ignored: this wildcard form matches fetches but has no effect on sandboxed commands)

### Denied (0)

None.

## Findings

- high domain-wildcard-broad (project) `* (allowedDomains)`: allows every host
- high domain-wildcard-broad (project) `*.com (allowedDomains)`: allows every host under the top-level domain .com
- high excluded-command-broad (project) `bash *`: runs a shell (bash) outside the sandbox with your full access
- high excluded-command-broad (project) `curl *`: runs a network tool (curl) outside the sandbox with your full access
- high filesystem-disabled (user) `sandbox.filesystem.disabled`: sandboxed commands can read and write the whole filesystem; denyRead and credentials file deny entries are not enforced, and with autoAllowBashIfSandboxed they run without prompts and can write files that widen their own access (shell startup files, $PATH executables, ~/.claude/settings.json)
- high repo-loosens (project) `allowedDomains: *`: set in the committed .claude/settings.json, so anyone who clones the repository gets it
- high repo-loosens (project) `allowedDomains: *.blob.core.windows.net`: set in the committed .claude/settings.json, so anyone who clones the repository gets it
- high repo-loosens (project) `allowedDomains: *.com`: set in the committed .claude/settings.json, so anyone who clones the repository gets it
- high repo-loosens (project) `excludedCommands: bash *`: set in the committed .claude/settings.json, so anyone who clones the repository gets it
- high repo-loosens (project) `excludedCommands: curl *`: set in the committed .claude/settings.json, so anyone who clones the repository gets it
- high repo-loosens (project) `excludedCommands: python scripts/load_data.py *`: set in the committed .claude/settings.json, so anyone who clones the repository gets it
- high unix-sockets-all (user) `sandbox.network.allowAllUnixSockets`: every Unix socket is open to sandboxed commands; a socket such as /var/run/docker.sock gives access to the host
- medium credentials-readable (default) `.env`: .env files in the project: filesystem isolation is off, so read blocks are not enforced
- medium credentials-readable (default) `~/.aws`: AWS credentials: filesystem isolation is off, so read blocks are not enforced
- medium credentials-readable (default) `~/.config/gh`: GitHub CLI token: filesystem isolation is off, so read blocks are not enforced
- medium credentials-readable (default) `~/.netrc`: netrc passwords: filesystem isolation is off, so read blocks are not enforced
- medium credentials-readable (default) `~/.ssh`: SSH keys: filesystem isolation is off, so read blocks are not enforced
- medium domain-wildcard-broad (project) `*.blob.core.windows.net (allowedDomains)`: covers hosts anyone can publish to (blob.core.windows.net, in the default list)
- medium domain-wildcard-broad (local) `*.ngrok.io (WebFetch(domain:) allow rule)`: covers hosts anyone can publish to (ngrok.io, in the default list)
- medium escape-hatch-open (default) `sandbox.allowUnsandboxedCommands`: Claude can retry a failed command unsandboxed (no prompt in bypassPermissions mode, or when an allow rule matches); set it to false, or add the ask rule Bash(dangerouslyDisableSandbox:true)
- medium excluded-command-broad (project) `python scripts/load_data.py *`: runs an interpreter (python) outside the sandbox with your full access
- medium fail-open (default) `sandbox.failIfUnavailable`: if the sandbox cannot start (missing dependency, unsupported platform) commands run unsandboxed
- medium strict-allowlist-ignored-scope (local) `sandbox.network.strictAllowlist`: has no effect in project or local settings; set it in user or managed settings

## Verify enforcement

Printed, not run. Ask Claude to run each line as a sandboxed Bash command in a session (a line typed at the `!` prompt usually runs outside the sandbox), and decline any offer to retry outside the sandbox.

```bash
touch ~/sandbox-probe  # fails (Operation not permitted or Read-only file system)
curl --noproxy '*' https://example.com  # fails with Could not resolve host
curl -sS -o /dev/null -w "%{http_code}" https://<a host under com>  # connects (any HTTP status from the server, not a proxy 403)
curl -sS -o /dev/null -w "%{http_code}" https://<a host under blob.core.windows.net>  # connects (any HTTP status from the server, not a proxy 403)
curl -sS -o /dev/null -w "%{http_code}" https://registry.npmjs.org  # connects (any HTTP status from the server, not a proxy 403)
curl -sS -o /dev/null -w "%{http_code}" https://<a host under ngrok.io>  # connects (any HTTP status from the server, not a proxy 403)
```
