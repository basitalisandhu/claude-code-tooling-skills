"""Builders for synthetic Claude Code transcript lines, shared by the transcript skill tests.

Every value is made up. The shapes follow the keys seen in local transcripts (2026-10-26); the format itself is not
documented, which is why the scripts read it defensively.
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "transcripts"


def base(kind: str, sid: str, ts: str, side: bool = False, cwd: str = "/srv/demo") -> dict:
    return {"type": kind, "sessionId": sid, "timestamp": ts, "uuid": f"u-{ts}", "isSidechain": side, "cwd": cwd}


def user(sid: str, ts: str, text: str, **kw) -> dict:
    return {**base("user", sid, ts, **kw), "message": {"role": "user", "content": text}}


def assistant(
    sid: str,
    ts: str,
    mid: str,
    model: str = "claude-demo-large",
    inp: int = 1,
    out: int = 10,
    read: int = 0,
    w5: int = 0,
    w1: int = 0,
    blocks: list | None = None,
    side: bool = False,
    rid: str | None = None,
    cwd: str = "/srv/demo",
) -> dict:
    d = base("assistant", sid, ts, side=side, cwd=cwd)
    d["requestId"] = rid or f"req-{mid}"
    d["message"] = {
        "id": mid,
        "model": model,
        "content": blocks or [{"type": "text", "text": "ok"}],
        "usage": {
            "input_tokens": inp,
            "output_tokens": out,
            "cache_read_input_tokens": read,
            "cache_creation_input_tokens": w5 + w1,
            "cache_creation": {"ephemeral_5m_input_tokens": w5, "ephemeral_1h_input_tokens": w1},
        },
    }
    return d


def tool_use(tid: str, name: str, inp: dict) -> dict:
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def tool_result(sid: str, ts: str, tid: str, text, is_error: bool | None = None, tur=None, cwd="/srv/demo") -> dict:
    block = {"type": "tool_result", "tool_use_id": tid, "content": text}
    if is_error is not None:
        block["is_error"] = is_error
    d = {**base("user", sid, ts, cwd=cwd), "message": {"role": "user", "content": [block]}}
    if tur is not None:
        d["toolUseResult"] = tur
    return d


def boundary(sid: str, ts: str, trigger: str = "auto", pre: int = 150000, post: int = 9000) -> dict:
    return {
        **base("system", sid, ts),
        "subtype": "compact_boundary",
        "content": "Conversation compacted",
        "compactMetadata": {"trigger": trigger, "preTokens": pre, "postTokens": post},
    }


def summary(sid: str, ts: str, text: str) -> dict:
    return {**user(sid, ts, text), "isCompactSummary": True}


def write_jsonl(path: Path, records: list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [r if isinstance(r, str) else json.dumps(r) for r in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path
