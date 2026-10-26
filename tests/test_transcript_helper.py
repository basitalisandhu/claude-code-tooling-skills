"""Tests for _transcript.py, the transcript reader shared (as identical copies) by the three transcript skills."""

from __future__ import annotations

from datetime import date

import pytest
from conftest import SKILLS, load_script
from transcript_builders import write_jsonl

tx = load_script("session-usage-ledger", "_transcript.py")


def test_every_copy_is_identical():
    copies = sorted(SKILLS.glob("*/scripts/_transcript.py"))
    assert len(copies) == 3
    assert len({p.read_bytes() for p in copies}) == 1, [str(p) for p in copies]


def test_collect_files_recurses_and_dedupes(tmp_path):
    a = write_jsonl(tmp_path / "p" / "a.jsonl", [{"type": "user"}])
    write_jsonl(tmp_path / "p" / "a" / "subagents" / "b.jsonl", [{"type": "user"}])
    (tmp_path / "p" / "notes.txt").write_text("x", encoding="utf-8")
    files = tx.collect_files([str(tmp_path), str(a)])
    assert sorted(f.name for f in files) == ["a.jsonl", "b.jsonl"]
    with pytest.raises(tx.InputError):
        tx.collect_files([str(tmp_path / "missing")])


def test_read_records_counts_problems(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_bytes(b'{"type": "user"}\n\nnot json\n[1]\n\xff\xfe\n{"type": "brand-new"}\n{"type": "pr-link"}\n')
    stats = tx.ReadStats()
    recs = tx.read_records([p], stats)
    assert [r.type for r in recs] == ["user", "pr-link"]
    assert stats.lines == 6 and stats.unreadable == 3 and stats.unknown_types == {"brand-new": 1}


def test_timestamps_ranges_and_projects(tmp_path):
    ts = tx.parse_ts("2026-10-05T23:30:00.000Z")
    assert ts.date() == date(2026, 10, 5) and tx.parse_ts("nope") is None
    assert tx.in_window(ts, date(2026, 10, 5), date(2026, 10, 5))
    assert not tx.in_window(None, date(2026, 10, 5), None)
    assert tx.parse_range("2026-10-01..2026-10-07", "--x") == (date(2026, 10, 1), date(2026, 10, 7))
    with pytest.raises(tx.InputError):
        tx.parse_range("2026-10-07..2026-10-01", "--x")
    sub = tmp_path / "proj" / "sess" / "subagents" / "workflows" / "w" / "a.jsonl"
    assert tx.project_name(sub) == "proj"
    assert tx.project_name(tmp_path / "proj" / "sess.jsonl") == "proj"
