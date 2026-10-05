"""Tests for trigger_eval.py. Each test writes synthetic skills and prompt sets into tmp_path."""

from __future__ import annotations

import json

from conftest import load_script, run_json, run_main, skill_md, write_files

mod = load_script("skill-trigger-eval", "trigger_eval.py")
DECISION = (
    "Keep a decision log of operational decisions with review dates and supersede links. "
    'Use when asked "which decisions are due for review?" or to record a decision. '
    "Not for architecture decision records with options analysis."
)
PROMPTS = """
decision-log:
  should_trigger:
    - "Which decisions are due for review?"
    - record a decision to keep the logs
  should_not_trigger:
    - "Write an architecture decision record with options analysis"
    - "Summarise yesterday's meeting actions"
"""


def setup(tmp_path, desc: str = DECISION, prompts: str = PROMPTS):
    write_files(tmp_path, {"skills/decision-log/SKILL.md": skill_md("decision-log", desc), "prompts.yaml": prompts})
    return str(tmp_path / "prompts.yaml"), str(tmp_path / "skills")


def test_scores_each_prompt_and_meets_targets(tmp_path):
    prompts, skills = setup(tmp_path)
    rc, rep = run_json(mod, [prompts, "--skill", skills])
    assert rc == 0
    r = rep["results"][0]
    assert (r["tp"], r["fn"], r["fp"], r["tn"]) == (2, 0, 0, 2)
    assert r["precision"] == 1.0 and r["recall"] == 1.0
    first = r["prompts"][0]
    assert first["phrase"] == 1.0 and first["triggered"] is True


def test_not_for_sentence_pushes_a_near_miss_down(tmp_path):
    prompts, skills = setup(tmp_path)
    _, rep = run_json(mod, [prompts, "--skill", skills])
    adr = next(p for p in rep["results"][0]["prompts"] if p["prompt"].startswith("Write an architecture"))
    assert adr["not_for"] > 0 and adr["triggered"] is False


def test_missed_prompt_fails_recall_target(tmp_path):
    prompts, skills = setup(tmp_path, prompts=PROMPTS + "\n" + "")
    write_files(
        tmp_path,
        {
            "prompts.yaml": PROMPTS.replace(
                "    - record a decision",
                '    - "what did we agree about the staging freeze?"\n    - record a decision',
            )
        },
    )
    rc, rep = run_json(mod, [prompts, "--skill", skills])
    assert rc == 1
    r = rep["results"][0]
    assert r["fn"] == 1 and r["recall"] == round(2 / 3, 4) and r["ok"] is False
    rc, rep = run_json(mod, [prompts, "--skill", skills, "--min-recall", "0.5"])
    assert rc == 0


def test_compare_two_versions_reports_flips(tmp_path):
    prompts, _ = setup(tmp_path)
    write_files(tmp_path, {"old.txt": "Keep a log of things.", "new.txt": DECISION})
    rc, rep = run_json(
        mod, [prompts, "--compare", str(tmp_path / "old.txt"), str(tmp_path / "new.txt"), "--name", "decision-log"]
    )
    assert rc == 0 and rep["compare"]["ok"] is True
    assert [r["version"] for r in rep["results"]] == ["old", "new"]
    assert any(f["new"] and not f["old"] for f in rep["compare"]["flips"])
    rc, rep = run_json(
        mod, [prompts, "--compare", str(tmp_path / "new.txt"), str(tmp_path / "old.txt"), "--name", "decision-log"]
    )
    assert rc == 1 and rep["compare"]["ok"] is False


def test_cross_counts_sibling_prompts_as_negatives(tmp_path):
    write_files(
        tmp_path,
        {
            "skills/a/SKILL.md": skill_md(
                "a", 'Review release notes for a tag. Use when "check the release notes". Not for x.'
            ),
            "skills/b/SKILL.md": skill_md(
                "b", 'Draft release notes from commits. Use when "write release notes". Not for y.'
            ),
            "p.json": json.dumps(
                {"a": {"should_trigger": ["check the release notes"]}, "b": {"should_trigger": ["write release notes"]}}
            ),
        },
    )
    _, rep = run_json(mod, [str(tmp_path / "p.json"), "--skill", str(tmp_path / "skills"), "--cross"])
    labels = {r["skill"]: [p["label"] for p in r["prompts"]] for r in rep["results"]}
    assert labels == {"a": ["pos", "cross"], "b": ["pos", "cross"]}


def test_empty_and_malformed_prompt_sets_exit_2(tmp_path):
    _, skills = setup(tmp_path)
    write_files(tmp_path, {"empty.yaml": "# nothing\n", "bad.yaml": "decision-log:\n  - stray\n", "bad.json": "{"})
    for name in ("empty.yaml", "bad.yaml", "bad.json", "missing.yaml"):
        rc, _, err = run_main(mod, [str(tmp_path / name), "--skill", skills])
        assert rc == 2 and err.startswith("trigger_eval.py:"), name


def test_no_matching_skill_and_no_skill_flag_exit_2(tmp_path):
    prompts, _ = setup(tmp_path)
    write_files(tmp_path, {"other/x/SKILL.md": skill_md("x", DECISION)})
    rc, _, err = run_main(mod, [prompts, "--skill", str(tmp_path / "other")])
    assert rc == 2 and "none of the skills" in err
    rc, _, err = run_main(mod, [prompts])
    assert rc == 2 and "--skill" in err


def test_scoring_is_transparent_and_deterministic():
    prof = mod.profile(DECISION)
    s = mod.score("Which decisions are due for review?", prof)
    assert s["coverage"] == 1.0 and s["phrase"] == 1.0
    assert s["score"] == round(0.5 * s["coverage"] + 0.2 * s["bigram"] + 0.5 * s["phrase"] - 0.5 * s["not_for"], 4)
    assert mod.score("", prof)["score"] == 0.0
    assert mod.stem("decisions") == "decision" and mod.stem("reviewing") == "review"


def test_golden_markdown(tmp_path):
    prompts, skills = setup(tmp_path)
    rc, out, _ = run_main(mod, [prompts, "--skill", skills])
    assert rc == 0
    assert out.startswith("# Skill trigger evaluation (lexical proxy)\n\nThreshold 0.35; score = 0.5 coverage")
    assert "| decision-log | 1.00 | 1.00 | 2 | 0 | 0 | 2 | ok |\n" in out
    assert out.endswith("## Misjudged prompts\n\nNone.\n")
