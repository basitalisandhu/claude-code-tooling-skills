"""Tests for usage_ledger.py. Inputs are the committed synthetic fixtures or transcripts built in tmp_path."""

from __future__ import annotations

import json

from conftest import load_script, run_json, run_main
from transcript_builders import FIXTURES, assistant, user, write_jsonl

mod = load_script("session-usage-ledger", "usage_ledger.py")
USAGE = str(FIXTURES / "usage")


def test_fixture_totals_dedupe_and_read_counts():
    rc, r = run_json(mod, [USAGE])
    assert rc == 1  # the default cache-hit threshold flags the fixture
    s = r["summary"]
    assert s["calls"] == 14 and s["sessions"] == 4
    assert r["read"]["repeated_lines_merged"] == 1
    assert r["read"]["unreadable_lines"] == 1
    assert r["read"]["unknown_types"] == {"future-bookkeeping": 1}
    assert s["write_5m"] == 287800 and s["write_1h"] == 67000
    # the split response counts its larger output once (450, not 120 + 450)
    assert s["output"] == 6590


def test_split_lines_keep_largest_usage(tmp_path):
    log = write_jsonl(
        tmp_path / "p" / "s.jsonl",
        [
            assistant("s", "2026-10-01T10:00:00Z", "m1", out=5, read=100),
            assistant("s", "2026-10-01T10:00:01Z", "m1", out=40, read=100),
            assistant("s", "2026-10-01T10:01:00Z", "m2", out=7, read=200),
        ],
    )
    rc, r = run_json(mod, [str(log), "--min-hit-ratio", "0"])
    assert rc == 0
    assert r["summary"]["calls"] == 2 and r["summary"]["output"] == 47 and r["summary"]["cache_read"] == 300


def test_hit_ratio_formula_and_first_call(tmp_path):
    log = write_jsonl(
        tmp_path / "p" / "s.jsonl",
        [
            assistant("s", "2026-10-01T10:00:00Z", "m1", inp=10, read=0, w1=90),
            assistant("s", "2026-10-01T10:01:00Z", "m2", inp=10, read=90, w1=0),
        ],
    )
    rc, r = run_json(mod, [str(log), "--min-hit-ratio", "0"])
    s = r["summary"]
    assert s["cache_hit_ratio"] == round(90 / (90 + 90 + 20), 4)
    assert s["first_call_median"] == 100
    assert r["sessions"][0]["first_call"] == 100


def test_subagent_share_from_sidechain_and_folder(tmp_path):
    proj = tmp_path / "proj"
    write_jsonl(proj / "s.jsonl", [assistant("s", "2026-10-01T10:00:00Z", "m1", inp=100)])
    write_jsonl(proj / "s" / "subagents" / "a.jsonl", [assistant("s", "2026-10-01T10:00:30Z", "m2", inp=100)])
    rc, r = run_json(mod, [str(proj), "--min-hit-ratio", "0"])
    assert r["summary"]["subagent_calls"] == 1
    assert r["summary"]["subagent_share"] == 0.5
    assert [p["key"] for p in r["projects"]] == ["proj"]


def test_compare_weeks_names_the_component_that_moved():
    rc, r = run_json(mod, [USAGE, "--compare-weeks", "--expect-ttl", "1h", "--min-hit-ratio", "0"])
    assert rc == 1
    ids = {f["id"] for f in r["findings"]}
    assert ids == {"cache-ttl-5m", "period-jump"}
    moved = " ".join(r["comparison"]["moved"])
    assert "1-hour writes turned into 5-minute writes" in moved
    assert "Cache-hit ratio fell" in moved
    assert r["comparison"]["metrics"]["share_5m_of_writes"]["change_points"] == 1.0


def test_baseline_and_period_ranges():
    rc, r = run_json(
        mod,
        [USAGE, "--baseline", "2026-10-06..2026-10-06", "--period", "2026-10-08..2026-10-08", "--min-hit-ratio", "0"],
    )
    comp = r["comparison"]
    assert comp["baseline"]["calls"] == 3 and comp["period"]["calls"] == 3
    assert comp["baseline"]["days"] == 1


def test_since_until_window():
    rc, r = run_json(mod, [USAGE, "--since", "2026-10-13", "--until", "2026-10-13", "--min-hit-ratio", "0"])
    assert r["summary"]["calls"] == 4 and [d["key"] for d in r["days"]] == ["2026-10-13"]


def test_first_call_threshold_finding():
    rc, r = run_json(mod, [USAGE, "--min-hit-ratio", "0", "--max-first-call", "40000"])
    assert rc == 1
    assert [f["id"] for f in r["findings"]] == ["first-call-overhead"]


def test_rates_file_estimates_cost(tmp_path):
    rates = tmp_path / "rates.json"
    rates.write_text(json.dumps({"claude-demo-": {"input": 1, "output": 2, "cache_read": 0.5}}), encoding="utf-8")
    log = write_jsonl(tmp_path / "p" / "s.jsonl", [assistant("s", "2026-10-01T10:00:00Z", "m1", inp=1_000_000)])
    rc, r = run_json(mod, [str(log), "--rates", str(rates), "--min-hit-ratio", "0"])
    assert r["summary"]["estimated_cost"] == 1.0 and r["summary"]["unpriced_calls"] == 0


def test_text_and_markdown_render():
    rc, out, _ = run_main(mod, [USAGE, "--format", "markdown", "--compare-weeks"])
    assert out.startswith("# Session usage ledger") and "| Day |" in out and "## What moved" in out
    rc, out, _ = run_main(mod, [USAGE])
    assert out.startswith("Session usage ledger") and "Per model\n---------" in out


def test_bad_inputs_exit_2(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("not json\n[1, 2]\n", encoding="utf-8")
    binary = tmp_path / "bin.jsonl"
    binary.write_bytes(b"\xff\xfe\x00garbage\n")
    no_usage = write_jsonl(tmp_path / "u.jsonl", [user("s", "2026-10-01T10:00:00Z", "hello")])
    for argv in (
        [str(tmp_path / "missing")],
        [str(empty)],
        [str(binary)],
        [str(no_usage)],
        [],
        [USAGE, "--since", "yesterday"],
        [USAGE, "--baseline", "2026-10-01..2026-10-02"],
        [USAGE, "--rates", str(empty)],
        [USAGE, "--out", str(tmp_path / "no-such-dir" / "x.txt")],
    ):
        rc, out, err = run_main(mod, argv)
        assert rc == 2, argv
        assert err.startswith("usage_ledger.py") or err.startswith("usage:"), (argv, err)
        assert "Traceback" not in err


def test_out_file_written(tmp_path):
    target = tmp_path / "ledger.json"
    rc, out, _ = run_main(mod, [USAGE, "--json", "--out", str(target)])
    assert out == "" and json.loads(target.read_text(encoding="utf-8"))["summary"]["calls"] == 14
