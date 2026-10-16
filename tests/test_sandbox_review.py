"""Tests for sandbox_review.py.

The synthetic project folders (locked-down, wide-open, repo-loosens, managed-overrides, malformed JSON, wrong types)
are defined in FIXTURES and written into tmp_path by each test, like the rest of the suite. The expected reports for
four of them are golden files in tests/golden/sandbox_review/; the reports name scopes and file names only, never
the temporary folder, so they are the same on every platform. Set UPDATE_GOLDEN=1 to rewrite them after a deliberate
change, then review the diff.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import ROOT, load_script, run_json, run_main, write_files

mod = load_script("sandbox-config-review", "sandbox_review.py")
GOLDEN = Path(__file__).resolve().parent / "golden" / "sandbox_review"
CREDENTIAL_DENY = [{"path": p, "mode": "deny"} for p in ("~/.ssh", "~/.aws", "~/.config/gh", "~/.netrc")]


def js(data: dict) -> str:
    return json.dumps(data, indent=2)


FIXTURES: dict[str, dict[str, str]] = {
    # Managed settings require the sandbox, fail closed, close the escape hatch and protect credentials.
    "locked-down": {
        "managed.json": js(
            {
                "sandbox": {
                    "enabled": True,
                    "failIfUnavailable": True,
                    "allowUnsandboxedCommands": False,
                    "network": {"allowedDomains": ["registry.npmjs.org", "api.github.com"]},
                    "credentials": {"files": CREDENTIAL_DENY},
                }
            }
        ),
        "project/.claude/settings.json": js({"permissions": {"deny": ["Read(./.env)", "Read(./.env.*)"]}}),
    },
    # Everything a project and a user can open at once.
    "wide-open": {
        "user.json": js(
            {
                "sandbox": {
                    "filesystem": {"disabled": True},
                    "network": {"allowAllUnixSockets": True},
                }
            }
        ),
        "project/.claude/settings.json": js(
            {
                "sandbox": {
                    "enabled": True,
                    "excludedCommands": ["bash *", "curl *", "python scripts/load_data.py *"],
                    "network": {"allowedDomains": ["*", "*.com", "*.blob.core.windows.net", "registry.npmjs.org"]},
                }
            }
        ),
        "project/.claude/settings.local.json": js(
            {
                "sandbox": {"network": {"strictAllowlist": True}},
                "permissions": {"allow": ["WebFetch(domain:*.ngrok.io)", "WebFetch(domain:docs.example.*)"]},
            }
        ),
    },
    # A cloned repository ships loosening values; the developer's own user settings close the escape hatch.
    "repo-loosens": {
        "user.json": js({"sandbox": {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False}}),
        "project/.claude/settings.json": js(
            {
                "sandbox": {
                    "allowUnsandboxedCommands": True,
                    "excludedCommands": ["docker compose *"],
                    "filesystem": {"allowWrite": ["~/.local/bin"], "denyRead": ["~/.ssh", "~/.aws", ".env"]},
                    "network": {
                        "allowedDomains": ["*.githubusercontent.com", "pypi.org"],
                        "strictAllowlist": True,
                        "httpProxyPort": 8080,
                    },
                },
                "permissions": {"deny": ["Read(~/.config/gh/**)", "Read(~/.netrc)"]},
            }
        ),
    },
    # Managed settings make the sandbox admin-required, so the repository's loosening entries are ignored.
    "managed-overrides": {
        "managed.json": js(
            {
                "sandbox": {
                    "enabled": True,
                    "failIfUnavailable": True,
                    "allowUnsandboxedCommands": False,
                    "excludedCommands": ["gh *"],
                    "network": {"allowedDomains": ["github.com"], "deniedDomains": ["gist.github.com"]},
                    "filesystem": {"denyRead": [".env"]},
                    "credentials": {"files": CREDENTIAL_DENY},
                }
            }
        ),
        "project/.claude/settings.json": js(
            {
                "sandbox": {
                    "enabled": False,
                    "excludedCommands": ["docker *"],
                    "network": {"allowedDomains": ["*.com"]},
                },
                "permissions": {"allow": ["WebFetch(domain:gist.github.com)"]},
            }
        ),
        "project/.claude/settings.local.json": js({"sandbox": {"network": {"allowAllUnixSockets": True}}}),
    },
    "malformed": {"project/.claude/settings.json": '{"sandbox": {"enabled": true,,}\n'},
    "wrong-types": {
        "project/.claude/settings.json": js({"sandbox": {"enabled": True, "excludedCommands": "docker *"}})
    },
}


def build(tmp_path: Path, name: str) -> list[str]:
    """Write fixture `name` and return the arguments that point the script at it."""
    write_files(tmp_path, FIXTURES[name])
    args = ["--project", str(tmp_path / "project")]
    (tmp_path / "project").mkdir(exist_ok=True)
    for scope in ("user", "managed"):
        if (tmp_path / f"{scope}.json").is_file():
            args += [f"--{scope}", str(tmp_path / f"{scope}.json")]
    return args


def found(rep: dict) -> set[tuple[str, str, str]]:
    return {(f["rule"], f["severity"], f["item"]) for f in rep["findings"]}


def rules(rep: dict) -> set[str]:
    return {f["rule"] for f in rep["findings"]}


def check_golden(name: str, text: str) -> None:
    path = GOLDEN / name
    if os.environ.get("UPDATE_GOLDEN"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    assert text == path.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["locked-down", "wide-open", "repo-loosens", "managed-overrides"])
def test_golden_markdown(tmp_path, name):
    rc, out, err = run_main(mod, [*build(tmp_path, name), "--platform", "linux"])
    assert err == ""
    check_golden(f"{name}.md", out)
    assert rc == (0 if name in ("locked-down", "managed-overrides") else 1)


def test_golden_json_wide_open(tmp_path):
    rc, out, _ = run_main(mod, [*build(tmp_path, "wide-open"), "--platform", "linux", "--format", "json"])
    assert rc == 1
    check_golden("wide-open.json", out)


def test_locked_down_has_no_findings_at_any_level(tmp_path):
    rc, rep = run_json(mod, [*build(tmp_path, "locked-down"), "--platform", "macos", "--fail-on", "low"])
    assert rc == 0 and rep["findings"] == []
    assert rep["admin_required"] is True
    assert rep["effective"]["enabled"] == {"value": True, "source": "managed", "ignored": []}
    hosts = {d["host"] for d in rep["domains"]["allowed"] if d["honoured"]}
    assert hosts == {"registry.npmjs.org", "api.github.com"}


def test_wide_open_findings(tmp_path):
    rc, rep = run_json(mod, [*build(tmp_path, "wide-open"), "--platform", "linux"])
    assert rc == 1
    got = found(rep)
    assert ("excluded-command-broad", "high", "bash *") in got
    assert ("excluded-command-broad", "high", "curl *") in got
    assert ("excluded-command-broad", "medium", "python scripts/load_data.py *") in got
    assert ("domain-wildcard-broad", "high", "* (allowedDomains)") in got
    assert ("domain-wildcard-broad", "high", "*.com (allowedDomains)") in got
    assert ("domain-wildcard-broad", "medium", "*.blob.core.windows.net (allowedDomains)") in got
    assert ("domain-wildcard-broad", "medium", "*.ngrok.io (WebFetch(domain:) allow rule)") in got
    assert ("filesystem-disabled", "high", "sandbox.filesystem.disabled") in got
    assert ("unix-sockets-all", "high", "sandbox.network.allowAllUnixSockets") in got
    assert ("strict-allowlist-ignored-scope", "medium", "sandbox.network.strictAllowlist") in got
    # Filesystem isolation is off (from user settings), so no read block holds.
    assert {f["item"] for f in rep["findings"] if f["rule"] == "credentials-readable"} == {
        "~/.ssh",
        "~/.aws",
        "~/.config/gh",
        "~/.netrc",
        ".env",
    }
    assert rep["effective"]["filesystem.disabled"]["source"] == "user"
    # A WebFetch wildcard in a position other than the start matches fetches but not sandboxed commands.
    webfetch = {d["host"]: d for d in rep["domains"]["allowed"] if d["via"].startswith("WebFetch")}
    assert webfetch["*.ngrok.io"]["honoured"] is True
    assert webfetch["docs.example.*"]["honoured"] is False


def test_repo_loosens_and_user_false_holds(tmp_path):
    rc, rep = run_json(mod, [*build(tmp_path, "repo-loosens"), "--platform", "linux"])
    assert rc == 1
    assert rep["effective"]["allowUnsandboxedCommands"]["value"] is False
    assert rep["effective"]["allowUnsandboxedCommands"]["source"] == "user"
    got = found(rep)
    assert ("repo-loosens", "high", "excludedCommands: docker compose *") in got
    assert ("repo-loosens", "high", "filesystem.allowWrite: ~/.local/bin") in got
    assert ("repo-loosens", "high", "allowedDomains: *.githubusercontent.com") in got
    assert ("repo-loosens", "high", "network.httpProxyPort: 8080") in got
    assert ("repo-loosens", "low", "allowUnsandboxedCommands: true") in got
    assert ("proxy-port-set", "medium", "sandbox.network.httpProxyPort = 8080") in got
    assert ("excluded-command-broad", "medium", "docker compose *") in got
    assert "escape-hatch-open" not in rules(rep) and "fail-open" not in rules(rep)
    # denyRead and Read deny rules together cover every credential path.
    assert "credentials-readable" not in rules(rep)


def test_managed_overrides_ignore_repository_entries(tmp_path):
    rc, rep = run_json(mod, [*build(tmp_path, "managed-overrides"), "--platform", "linux", "--fail-on", "low"])
    assert rc == 1
    assert rep["admin_required"] is True
    assert rep["effective"]["enabled"]["value"] is True
    assert rep["effective"]["network.allowAllUnixSockets"]["value"] is None
    ignored = {(e["value"], e["honoured"]) for e in rep["lists"]["excludedCommands"]}
    assert ignored == {("gh *", True), ("docker *", False)}
    got = found(rep)
    assert ("excluded-command-broad", "low", "docker *") in got
    assert ("domain-wildcard-broad", "low", "*.com (allowedDomains)") in got
    assert ("allow-deny-conflict", "low", "gist.github.com") not in got  # the WebFetch rule is ignored here
    assert all(f["severity"] == "low" for f in rep["findings"])
    rc_high, _ = run_json(mod, [*build(tmp_path, "managed-overrides"), "--platform", "linux"])
    assert rc_high == 0


def test_malformed_json_exits_2(tmp_path):
    rc, out, err = run_main(mod, build(tmp_path, "malformed"))
    assert rc == 2 and out == ""
    assert "invalid JSON" in err


def test_wrong_types_exit_2(tmp_path):
    rc, _, err = run_main(mod, build(tmp_path, "wrong-types"))
    assert rc == 2 and "excludedCommands must be an array of strings" in err
    write_files(tmp_path / "b", {".claude/settings.json": js({"sandbox": {"enabled": "yes"}})})
    rc, _, err = run_main(mod, ["--project", str(tmp_path / "b")])
    assert rc == 2 and "enabled must be true or false" in err
    write_files(tmp_path / "c", {".claude/settings.json": js({"sandbox": {"credentials": {"files": [{"path": 1}]}}})})
    rc, _, err = run_main(mod, ["--project", str(tmp_path / "c")])
    assert rc == 2 and "credentials.files[0]" in err
    write_files(tmp_path / "d", {".claude/settings.json": "[1, 2]\n"})
    assert run_main(mod, ["--project", str(tmp_path / "d")])[0] == 2


def test_bad_usage_exits_2(tmp_path):
    assert run_main(mod, [])[0] == 2
    assert run_main(mod, ["--project", str(tmp_path / "missing")])[0] == 2
    assert run_main(mod, ["--user", str(tmp_path / "missing.json")])[0] == 2


def test_empty_project_reports_sandbox_off_and_skips_active_checks(tmp_path):
    write_files(tmp_path / "p", {".claude/settings.json": ""})
    rc, rep = run_json(mod, ["--project", str(tmp_path / "p"), "--platform", "macos"])
    assert rc == 1
    assert rep["active_checks"] is False
    assert [(f["rule"], f["detail"]) for f in rep["findings"]] == [
        ("sandbox-off", "not set (the sandbox is off by default)")
    ]


def test_windows_native_is_unsandboxed(tmp_path):
    write_files(
        tmp_path / "p", {".claude/settings.json": js({"sandbox": {"enabled": True, "failIfUnavailable": True}})}
    )
    rc, rep = run_json(mod, ["--project", str(tmp_path / "p"), "--platform", "windows"])
    assert rc == 1 and rules(rep) == {"windows-native-unsandboxed"}
    assert "exits at startup" in rep["findings"][0]["detail"]


def test_escape_hatch_closed_by_ask_rule_and_fail_on_levels(tmp_path):
    settings = {"sandbox": {"enabled": True}, "permissions": {"ask": ["Bash(dangerouslyDisableSandbox:true)"]}}
    write_files(tmp_path / "p", {".claude/settings.local.json": js(settings)})
    args = ["--project", str(tmp_path / "p"), "--platform", "linux"]
    rc, rep = run_json(mod, args)
    assert "escape-hatch-open" not in rules(rep) and "fail-open" in rules(rep)
    assert rc == 0  # only medium findings, default --fail-on high
    assert run_json(mod, [*args, "--fail-on", "medium"])[0] == 1


def test_credential_coverage_rules(tmp_path):
    settings = {
        "sandbox": {
            "enabled": True,
            "filesystem": {"denyRead": ["~/"], "allowRead": ["~/.ssh/config", "~/.aws"]},
            "credentials": {"files": [{"path": "~/.netrc", "mode": "mask"}]},
        },
        "permissions": {"deny": ["Read(**/.env)"]},
    }
    write_files(tmp_path / "p", {".claude/settings.json": js(settings)})
    _, rep = run_json(mod, ["--project", str(tmp_path / "p"), "--platform", "linux"])
    readable = {f["item"] for f in rep["findings"] if f["rule"] == "credentials-readable"}
    # ~/.aws is re-opened by a narrower allowRead; a project mask entry is ignored, but ~/ still covers ~/.netrc.
    assert readable == {"~/.aws"}
    user = {"permissions": {"blockReadsOutsideWorkingDirectories": True}}
    write_files(tmp_path, {"user.json": js(user)})
    write_files(tmp_path / "q", {".claude/settings.json": js({"sandbox": {"enabled": True}})})
    _, rep = run_json(
        mod, ["--project", str(tmp_path / "q"), "--user", str(tmp_path / "user.json"), "--platform", "linux"]
    )
    assert {f["item"] for f in rep["findings"] if f["rule"] == "credentials-readable"} == {".env"}


def test_strict_allowlist_in_user_settings_ignores_repository_domains(tmp_path):
    write_files(tmp_path, {"user.json": js({"sandbox": {"enabled": True, "network": {"strictAllowlist": True}}})})
    write_files(
        tmp_path / "p",
        {
            ".claude/settings.json": js(
                {"sandbox": {"network": {"allowedDomains": ["*.amazonaws.com"]}}, "permissions": {"allow": []}}
            )
        },
    )
    _, rep = run_json(
        mod, ["--project", str(tmp_path / "p"), "--user", str(tmp_path / "user.json"), "--platform", "linux"]
    )
    assert [d["honoured"] for d in rep["domains"]["allowed"]] == [False]
    assert ("domain-wildcard-broad", "low", "*.amazonaws.com (allowedDomains)") in found(rep)
    assert ("repo-loosens", "low", "allowedDomains: *.amazonaws.com") in found(rep)
    assert rep["effective"]["network.strictAllowlist"]["source"] == "user"


def test_filesystem_disabled_without_auto_allow_is_medium_and_ignored_in_project(tmp_path):
    user = {"sandbox": {"enabled": True, "autoAllowBashIfSandboxed": False, "filesystem": {"disabled": True}}}
    write_files(tmp_path, {"user.json": js(user)})
    rc, rep = run_json(mod, ["--user", str(tmp_path / "user.json"), "--platform", "linux"])
    assert ("filesystem-disabled", "medium", "sandbox.filesystem.disabled") in found(rep)
    write_files(tmp_path / "p", {".claude/settings.json": js({"sandbox": {"filesystem": {"disabled": True}}})})
    _, rep = run_json(mod, ["--project", str(tmp_path / "p"), "--platform", "linux"])
    assert rep["effective"]["filesystem.disabled"]["value"] is False
    assert ("repo-loosens", "low", "filesystem.disabled: true") in found(rep)


def test_verify_list_is_printed_with_allowed_refused_and_denied_hosts(tmp_path):
    settings = {
        "sandbox": {"enabled": True, "network": {"allowedDomains": ["example.com", "*.example.org"]}},
        "permissions": {
            "allow": ["WebFetch(domain:docs.example.net)"],
            "deny": ["WebFetch(domain:upload.example.com)"],
        },
    }
    write_files(tmp_path / "p", {".claude/settings.local.json": js(settings)})
    rc, out, _ = run_main(
        mod, ["--project", str(tmp_path / "p"), "--platform", "macos", "--out", str(tmp_path / "r.md")]
    )
    assert out == ""
    text = (tmp_path / "r.md").read_text(encoding="utf-8")
    curl = 'curl -sS -o /dev/null -w "%{http_code}" https://'
    assert f"{curl}example.com  # connects" in text
    assert f"{curl}docs.example.net  # connects" in text
    assert f"{curl}<a host under example.org>" in text
    # example.org may match *.example.org (the page does not say), so the refused probe is example.net.
    assert f"{curl}example.net  # refused" in text
    assert f"{curl}upload.example.com  # refused in every permission mode" in text


def test_cli_dispatches_sandbox_review(tmp_path):
    write_files(tmp_path / "p", {".claude/settings.json": js({"sandbox": {"enabled": False}})})
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "cli.py"),
            "sandbox-review",
            "--project",
            str(tmp_path / "p"),
            "--platform",
            "linux",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1
    off = [f for f in json.loads(result.stdout)["findings"] if f["rule"] == "sandbox-off"]
    assert off[0]["detail"] == "set to false in project settings"
