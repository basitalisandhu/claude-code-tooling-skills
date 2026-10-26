"""Tests for shell_slips.py. Inputs are the committed synthetic fixtures or transcripts built in tmp_path."""

from __future__ import annotations

from conftest import load_script, run_json, run_main
from transcript_builders import FIXTURES, assistant, tool_result, tool_use, user, write_jsonl

mod = load_script("shell-slip-audit", "shell_slips.py")
SHELL = str(FIXTURES / "shell")


def session(tmp_path, pairs, tool="Bash", cwd="/srv/demo", name="s.jsonl"):
    """pairs: (command, result text, is_error) per call."""
    recs = [user("s1", "2026-10-20T09:00:00Z", "go", cwd=cwd)]
    for i, (cmd, out, err) in enumerate(pairs):
        ts = f"2026-10-20T09:{i + 1:02d}:00Z"
        recs.append(assistant("s1", ts, f"m{i}", blocks=[tool_use(f"t{i}", tool, {"command": cmd})], cwd=cwd))
        recs.append(tool_result("s1", ts, f"t{i}", out, is_error=err, cwd=cwd))
    return write_jsonl(tmp_path / "p" / name, recs)


def patterns(report):
    return {p["pattern"]: p for p in report["patterns"]}


def test_fixture_counts_rate_and_silent():
    rc, r = run_json(mod, [SHELL])
    assert rc == 1
    s = r["summary"]
    assert s["shell_calls"] == 14 and s["bash_calls"] == 12 and s["powershell_calls"] == 2
    assert s["slip_calls"] == 9 and s["slips_per_1000"] == 642.9
    assert s["silent_slip_calls"] == 3 and s["stops"] == 1
    p = patterns(r)
    assert set(p) == {
        "glob-in-flag-value",
        "unmatched-glob",
        "equals-expansion",
        "bash-only-builtin",
        "bad-substitution",
        "heredoc-in-powershell",
        "bash-syntax-in-powershell",
        "windows-command-length",
        "timed-out",
    }
    assert p["glob-in-flag-value"]["repeats"] == 1 and p["glob-in-flag-value"]["silent"] == 2


def test_zsh_error_classification(tmp_path):
    log = session(
        tmp_path,
        [
            ("grep x . --include=*.py", "(eval):1: no matches found: --include=*.py", None),
            ("ls a/*.md", "zsh:1: no matches found: a/*.md", None),
            ("git log HEAD^", "(eval):1: bad pattern: HEAD^", None),
            ("x", "(eval):3: parse error near `)'", None),
            ("ls f(1).txt", "(eval):1: unknown file attribute: 1", None),
            ("git show $B:pkg.json", "(eval):1: unrecognized modifier `p'", None),
            ("frob --now", "(eval):1: command not found: frob", True),
        ],
    )
    rc, r = run_json(mod, [str(log)])
    assert set(patterns(r)) == {
        "glob-in-flag-value",
        "unmatched-glob",
        "bad-pattern",
        "parse-error",
        "unknown-file-attribute",
        "colon-modifier",
        "command-not-found",
    }
    assert r["summary"]["silent_slip_calls"] == 6


def test_error_text_mid_line_is_not_a_slip(tmp_path):
    log = session(tmp_path, [("cat notes.md", "The report quotes `(eval):1: no matches found` as an example.", None)])
    rc, r = run_json(mod, [str(log)])
    assert rc == 0 and r["summary"]["slip_calls"] == 0


def test_tool_use_result_stdout_is_read(tmp_path):
    recs = [
        assistant("s1", "2026-10-20T09:00:00Z", "m0", blocks=[tool_use("t0", "Bash", {"command": "ls x/*"})]),
        tool_result(
            "s1",
            "2026-10-20T09:00:01Z",
            "t0",
            [{"type": "text", "text": "partial"}],
            tur={"stdout": "", "stderr": "(eval):1: no matches found: x/*", "interrupted": False},
        ),
    ]
    log = write_jsonl(tmp_path / "p" / "s.jsonl", recs)
    rc, r = run_json(mod, [str(log)])
    assert "unmatched-glob" in patterns(r)


def test_interrupted_is_a_stop_not_a_slip(tmp_path):
    recs = [
        assistant("s1", "2026-10-20T09:00:00Z", "m0", blocks=[tool_use("t0", "Bash", {"command": "sleep 100"})]),
        tool_result("s1", "2026-10-20T09:00:01Z", "t0", "", tur={"interrupted": True}),
    ]
    log = write_jsonl(tmp_path / "p" / "s.jsonl", recs)
    rc, r = run_json(mod, [str(log)])
    assert rc == 0 and r["summary"]["stops"] == 1 and r["summary"]["slip_calls"] == 0


def test_long_command_only_flagged_on_windows(tmp_path):
    long_cmd = "echo " + "x" * 8100
    posix = session(tmp_path, [(long_cmd, "x", None)], name="posix.jsonl")
    rc, r = run_json(mod, [str(posix)])
    assert rc == 0 and r["summary"]["long_commands_not_windows"] == 1
    rc, r = run_json(mod, [str(posix), "--platform", "windows"])
    assert rc == 1 and "windows-command-length" in patterns(r)


def test_max_rate_and_since(tmp_path):
    rc, r = run_json(mod, [SHELL, "--max-rate", "700"])
    assert rc == 0 and r["flagged"] is False
    rc, r = run_json(mod, [SHELL, "--since", "2026-10-21"])
    assert r["summary"]["shell_calls"] == 4


def test_emit_rule_lists_found_patterns():
    rc, out, _ = run_main(mod, [SHELL, "--emit-rule"])
    assert rc == 1 and out.startswith("## Shell commands")
    assert "--include='*.ts'" in out and "here-string" in out and "(eval):N:" in out


def test_markdown_examples_are_truncated(tmp_path):
    rc, out, _ = run_main(mod, [SHELL, "--format", "markdown"])
    assert out.startswith("# Shell slip audit") and "| Pattern |" in out
    example = next(line for line in out.splitlines() if line.startswith("- `windows-command-length`"))
    assert "..." in example and len(example) < 260


def test_bad_inputs_exit_2(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text("{oops\n", encoding="utf-8")
    no_shell = write_jsonl(tmp_path / "n.jsonl", [user("s", "2026-10-01T10:00:00Z", "hi")])
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    for argv in (
        [str(bad)],
        [str(no_shell)],
        [str(empty_dir)],
        [str(tmp_path / "missing.jsonl")],
        [SHELL, "--until", "2026-13-01"],
        [SHELL, "--max-rate", "-1"],
        [SHELL, "--out", str(tmp_path / "nope" / "out.txt")],
    ):
        rc, _, err = run_main(mod, argv)
        assert rc == 2, argv
        assert "Traceback" not in err
