"""Tests for compaction_check.py. Inputs are the committed synthetic fixture or transcripts built in tmp_path."""

from __future__ import annotations

from conftest import load_script, run_json, run_main
from transcript_builders import FIXTURES, assistant, boundary, summary, tool_result, tool_use, user, write_jsonl

mod = load_script("compaction-loss-check", "compaction_check.py")
COMPACTION = str(FIXTURES / "compaction")


def statuses(b):
    return {(x["kind"], x["text"]): x["status"] for x in b["items"]}


def test_fixture_boundaries_triggers_and_idle():
    rc, r = run_json(mod, [COMPACTION])
    assert rc == 1
    s = r["summary"]
    assert s["boundaries"] == 2 and s["triggers"] == {"auto": 1, "idle": 1} and s["idle"] == 1
    first, second = r["boundaries"]
    assert first["pre_tokens"] == 167000 and first["post_tokens"] == 9800
    assert first["minutes_since_user_message"] == 6.0 and not first["idle"]
    assert second["minutes_since_user_message"] == 140.0


def test_fixture_items_checked_against_summary():
    rc, r = run_json(mod, [COMPACTION])
    st = statuses(r["boundaries"][0])
    assert st[("rule", "Never push to main.")] == "kept"
    assert st[("rule", "Always run npm test before you commit.")] == "missing"
    assert st[("file", "/srv/demo-shop/src/checkout/CouponField.tsx")] == "kept"  # base name in summary
    assert st[("file", "/srv/demo-shop/src/checkout/total.ts")] == "missing"
    assert st[("branch", "feature/coupon-field")] == "kept"
    assert st[("pr", "#41")] == "kept"
    assert st[("todo", "Update the order confirmation email")] == "missing"
    assert ("todo", "Add coupon field") not in st  # completed items are not open


def test_rule_partly_kept_when_most_words_present(tmp_path):
    log = write_jsonl(
        tmp_path / "p" / "s.jsonl",
        [
            user("s", "2026-10-01T10:00:00Z", "Only deploy from the release branch after review."),
            boundary("s", "2026-10-01T10:05:00Z"),
            summary("s", "2026-10-01T10:05:01Z", "The user wants deploys from the release branch after a review."),
        ],
    )
    rc, r = run_json(mod, [str(log)])
    assert rc == 0
    assert statuses(r["boundaries"][0]) == {("rule", "Only deploy from the release branch after review."): "partly"}


def test_non_rule_lines_and_reminders_ignored(tmp_path):
    log = write_jsonl(
        tmp_path / "p" / "s.jsonl",
        [
            user(
                "s",
                "2026-10-01T10:00:00Z",
                "Please add a footer.\n<system-reminder>You must never do this.</system-reminder>",
            ),
            boundary("s", "2026-10-01T10:05:00Z"),
            summary("s", "2026-10-01T10:05:01Z", "Footer work."),
        ],
    )
    rc, r = run_json(mod, [str(log)])
    assert rc == 0 and r["boundaries"][0]["items"] == []


def test_missing_summary_is_unverified_and_fails(tmp_path):
    log = write_jsonl(
        tmp_path / "p" / "s.jsonl",
        [
            user("s", "2026-10-01T10:00:00Z", "Never commit secrets."),
            boundary("s", "2026-10-01T10:05:00Z", trigger="manual"),
            user("s", "2026-10-01T10:06:00Z", "next task"),
        ],
    )
    rc, r = run_json(mod, [str(log)])
    assert rc == 1
    b = r["boundaries"][0]
    assert b["summary_found"] is False and statuses(b) == {("rule", "Never commit secrets."): "unverified"}


def test_auto_after_long_gap_is_idle_but_manual_is_not(tmp_path):
    log = write_jsonl(
        tmp_path / "p" / "s.jsonl",
        [
            user("s", "2026-10-01T10:00:00Z", "hello"),
            boundary("s", "2026-10-01T11:00:00Z", trigger="auto"),
            summary("s", "2026-10-01T11:00:01Z", "hello"),
            user("s", "2026-10-01T11:10:00Z", "again"),
            boundary("s", "2026-10-01T13:00:00Z", trigger="manual"),
            summary("s", "2026-10-01T13:00:01Z", "again"),
        ],
    )
    rc, r = run_json(mod, [str(log), "--idle-minutes", "45"])
    assert [b["idle"] for b in r["boundaries"]] == [True, False]


def test_task_tools_and_notebook_edits(tmp_path):
    log = write_jsonl(
        tmp_path / "p" / "s.jsonl",
        [
            user("s", "2026-10-01T10:00:00Z", "start"),
            assistant(
                "s",
                "2026-10-01T10:01:00Z",
                "m1",
                blocks=[
                    tool_use("a", "TaskCreate", {"subject": "Write migration"}),
                    tool_use("b", "TaskCreate", {"subject": "Update docs"}),
                    tool_use("c", "TaskUpdate", {"taskId": "1", "status": "completed"}),
                    tool_use("d", "NotebookEdit", {"notebook_path": "/srv/demo/analysis.ipynb"}),
                ],
            ),
            boundary("s", "2026-10-01T10:05:00Z"),
            summary("s", "2026-10-01T10:05:01Z", "Edited analysis.ipynb."),
        ],
    )
    rc, r = run_json(mod, [str(log)])
    st = statuses(r["boundaries"][0])
    assert st == {("file", "/srv/demo/analysis.ipynb"): "kept", ("todo", "Update docs"): "missing"}
    assert rc == 0  # a missing to-do alone does not fail the check


def test_pr_number_from_gh_pr_create_result(tmp_path):
    log = write_jsonl(
        tmp_path / "p" / "s.jsonl",
        [
            user("s", "2026-10-01T10:00:00Z", "open a PR"),
            assistant(
                "s", "2026-10-01T10:01:00Z", "m1", blocks=[tool_use("t1", "Bash", {"command": "gh pr create -f"})]
            ),
            tool_result("s", "2026-10-01T10:01:05Z", "t1", "https://github.com/example/app/pull/7"),
            boundary("s", "2026-10-01T10:05:00Z"),
            summary("s", "2026-10-01T10:05:01Z", "Opened a pull request."),
        ],
    )
    rc, r = run_json(mod, [str(log)])
    assert statuses(r["boundaries"][0]) == {("pr", "#7"): "missing"}


def test_emit_recap_and_markdown():
    rc, out, _ = run_main(mod, [COMPACTION, "--emit-recap"])
    assert rc == 1 and out.startswith("Re-stating context that the compaction at 2026-10-22 11:30 UTC")
    assert "- From now on, use pnpm instead of npm." in out and "- #41" in out
    rc, out, _ = run_main(mod, [COMPACTION, "--format", "markdown"])
    assert out.startswith("# Compaction loss check") and "Re-state these:" in out


def test_starts_after_earlier_compaction_is_reported(tmp_path):
    log = write_jsonl(
        tmp_path / "p" / "s.jsonl",
        [
            summary("s", "2026-10-01T09:00:00Z", "Earlier work summarised."),
            user("s", "2026-10-01T10:00:00Z", "continue"),
            boundary("s", "2026-10-01T10:05:00Z"),
            summary("s", "2026-10-01T10:05:01Z", "continue"),
        ],
    )
    rc, r = run_json(mod, [str(log)])
    assert r["summary"]["starts_compacted"] == 1


def test_bad_inputs_exit_2(tmp_path):
    no_boundary = write_jsonl(tmp_path / "a.jsonl", [user("s", "2026-10-01T10:00:00Z", "hi")])
    garbage = tmp_path / "g.jsonl"
    garbage.write_bytes(b"\xff\xff\n{bad json\n")
    for argv in (
        [str(no_boundary)],
        [str(garbage)],
        [str(tmp_path / "missing")],
        [],
        [COMPACTION, "--since", "2027-01-01"],
        [COMPACTION, "--idle-minutes", "0"],
        [COMPACTION, "--out", str(tmp_path / "no" / "dir.txt")],
    ):
        rc, _, err = run_main(mod, argv)
        assert rc == 2, argv
        assert "Traceback" not in err
