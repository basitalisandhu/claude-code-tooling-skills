"""Tests for description_lint.py. Each test writes synthetic SKILL.md files into tmp_path."""

from __future__ import annotations

from conftest import load_script, run_json, run_main, skill_md, write_files

mod = load_script("skill-description-linter", "description_lint.py")
GOOD = (
    'Review a plan before it ships. Use when asked "is this plan ready?" or before a review. '
    "Not for code review (use review-checklist)."
)


def rules(rep: dict) -> set[str]:
    return {f["rule"] for s in rep["skills"] for f in s["findings"]}


def test_clean_skill_exits_0_and_reports_listing_cost(tmp_path):
    write_files(tmp_path, {"plan-review/SKILL.md": skill_md("plan-review", GOOD)})
    rc, rep = run_json(mod, [str(tmp_path)])
    assert rc == 0 and rules(rep) == set()
    skill = rep["skills"][0]
    assert skill["description_chars"] == len(GOOD)
    assert skill["estimated_tokens"] == (len(GOOD) + 3) // 4
    assert skill["trigger_phrases"] == ["is this plan ready?"]


def test_empty_folder_and_missing_path_exit_2(tmp_path):
    rc, _, err = run_main(mod, [str(tmp_path)])
    assert rc == 2 and "no SKILL.md" in err
    rc, _, err = run_main(mod, [str(tmp_path / "nope")])
    assert rc == 2 and "not found" in err


def test_malformed_front_matter(tmp_path):
    write_files(
        tmp_path,
        {
            "a/SKILL.md": "# no front matter\n",
            "b/SKILL.md": "---\nname: b\ndescription: x\n",
            "c/SKILL.md": "---\nname: c\ndescription: Lint files: strictly\nname: c\n---\n## Limits\n",
        },
    )
    rc, rep = run_json(mod, [str(tmp_path)])
    by = {s["file"].split("/")[-2]: {f["rule"] for f in s["findings"]} for s in rep["skills"]}
    assert rc == 1
    assert by["a"] == {"front-matter-missing"}
    assert by["b"] == {"front-matter-unclosed"}
    assert "yaml-unsafe" in by["c"] and "description-not-double-quoted" in by["c"]


def test_each_description_rule(tmp_path):
    long_desc = "Review " + "word " * 130 + 'Use when "x y". Not for z.'
    write_files(
        tmp_path,
        {
            "too-long/SKILL.md": skill_md("too-long", long_desc),
            "verb/SKILL.md": skill_md("verb", 'This skill reviews. Use when "a b". Not for c.'),
            "hyphen/SKILL.md": skill_md("hyphen", 'Checklist-driven review. Use when "a b". Not for c.'),
            "phrase/SKILL.md": skill_md("phrase", "Review plans. Use when asked. Not for code."),
            "usewhen/SKILL.md": skill_md("usewhen", 'Review plans "a b". Not for code.'),
            "notfor/SKILL.md": skill_md("notfor", 'Review plans. Use when "a b".'),
            "limits/SKILL.md": skill_md("limits", GOOD, body="## Steps\n"),
            "folder/SKILL.md": skill_md("Other_Name", GOOD),
        },
    )
    rc, rep = run_json(mod, [str(tmp_path)])
    by = {s["file"].split("/")[-2]: {f["rule"] for f in s["findings"]} for s in rep["skills"]}
    assert rc == 1
    assert by["too-long"] == {"description-too-long"}
    assert by["verb"] == {"description-verb-start"}
    assert by["hyphen"] == {"description-verb-start"}
    assert by["phrase"] == {"description-no-trigger-phrase"}
    assert by["usewhen"] == {"description-no-use-when"}
    assert by["notfor"] == {"description-no-not-for"}
    assert by["limits"] == {"limits-missing"}
    assert by["folder"] == {"name-mismatch", "name-format"}


def test_max_chars_option(tmp_path):
    write_files(tmp_path, {"plan-review/SKILL.md": skill_md("plan-review", GOOD)})
    rc, rep = run_json(mod, [str(tmp_path), "--max-chars", "40"])
    assert rc == 1 and rules(rep) == {"description-too-long"}


def test_fix_quotes_plain_and_block_descriptions_in_place(tmp_path):
    tail = "license: MIT\n---\n## Limits\n"
    plain = '---\nname: a\ndescription: Review plans. Use when asked "ready?". Not for code.\n' + tail
    block = '---\nname: b\ndescription: >-\n  Review plans. Use when\n  asked "ready?". Not for code.\n' + tail
    write_files(tmp_path, {"a/SKILL.md": plain, "b/SKILL.md": block})
    rc, rep = run_json(mod, [str(tmp_path), "--fix"])
    assert rc == 0 and rep["fixed"] == 2
    a = (tmp_path / "a" / "SKILL.md").read_text(encoding="utf-8")
    b = (tmp_path / "b" / "SKILL.md").read_text(encoding="utf-8")
    assert 'description: "Review plans. Use when asked \\"ready?\\". Not for code."\n' in a
    assert 'description: "Review plans. Use when asked \\"ready?\\". Not for code."\nlicense: MIT\n' in b


def test_diff_shows_the_fix_and_writes_nothing(tmp_path):
    text = (
        '---\nname: a\ndescription: Review plans: carefully. Use when asked "ready?". Not for code.\n---\n## Limits\n'
    )
    write_files(tmp_path, {"a/SKILL.md": text})
    rc, out, _ = run_main(mod, [str(tmp_path), "--diff"])
    assert rc == 1
    assert '+description: "Review plans: carefully.' in out
    assert (tmp_path / "a" / "SKILL.md").read_text(encoding="utf-8") == text


def test_golden_markdown(tmp_path, monkeypatch):
    write_files(tmp_path, {"skills/plan-review/SKILL.md": skill_md("plan-review", GOOD, body="## Steps\n")})
    monkeypatch.chdir(tmp_path)
    rc, out, _ = run_main(mod, ["skills"])
    assert rc == 1
    n = len(GOOD)
    assert out == (
        "# Skill description lint\n\n"
        "| Skill | File | Chars | Est. tokens | Findings |\n|---|---|---|---|---|\n"
        f"| plan-review | `skills/plan-review/SKILL.md` | {n} | {(n + 3) // 4} | 1 |\n\n"
        f"1 skill(s), 1 finding(s), 0 file(s) fixed. Listing cost {n} characters, about {(n + 3) // 4} tokens "
        "(characters / 4).\n\n## Findings\n\n"
        "- `skills/plan-review/SKILL.md:5` limits-missing: the body has no '## Limits' section\n"
    )


def test_out_file_and_help(tmp_path):
    write_files(tmp_path, {"plan-review/SKILL.md": skill_md("plan-review", GOOD)})
    target = tmp_path / "report.md"
    rc, out, _ = run_main(mod, [str(tmp_path), "--out", str(target)])
    assert rc == 0 and out == "" and target.read_text(encoding="utf-8").startswith("# Skill description lint")
    rc, out, _ = run_main(mod, ["--help"])
    assert rc == 0 and out.startswith("usage: description_lint.py")
