"""Tests for _skillmd.py, the front matter reader shared (as identical copies) by six of the skill scripts."""

from __future__ import annotations

import pytest
from conftest import SKILLS, load_script

helper = load_script("skill-description-linter", "_skillmd.py")


def test_every_copy_is_identical():
    copies = sorted(SKILLS.glob("*/scripts/_skillmd.py"))
    assert len(copies) == 6
    texts = {p.read_bytes() for p in copies}
    assert len(texts) == 1, [str(p) for p in copies]


def test_scalar_styles_and_nested_values():
    fm = helper.parse(
        '---\nname: demo\ndescription: "Say \\"hi\\" now"\nother: \'it\'\'s\'\nlist: [a, "b"]\n'
        "items:\n  - one\n  - two\nmetadata:\n  author: Someone\n---\nbody\n"
    )
    assert fm.closed and fm.problems == []
    assert fm.text("description") == 'Say "hi" now' and fm.fields["description"].style == "double"
    assert fm.text("other") == "it's"
    assert fm.fields["list"].value == ["a", "b"]
    assert fm.fields["items"].value == ["one", "two"]
    assert fm.fields["metadata"].value == {"author": "Someone"}
    assert fm.body_start == 11


def test_block_scalars():
    folded = helper.parse("---\ndescription: >-\n  one\n  two\n\n  three\n---\n")
    literal = helper.parse("---\ndescription: |\n  one\n  two\n---\n")
    assert folded.text("description") == "one two\nthree"
    assert literal.text("description") == "one\ntwo"


@pytest.mark.parametrize(
    "line",
    [
        "description: Lint files: strictly",
        "description: Use for C # code",
        "description: *alias",
        'description: "never closed',
        "description: {a: 1}",
    ],
)
def test_strict_yaml_problems(line):
    fm = helper.parse(f"---\nname: x\n{line}\n---\n")
    assert len(fm.problems) == 1 and fm.problems[0][0] == 3


def test_duplicate_keys_unclosed_and_missing():
    assert helper.parse("---\nname: a\nname: b\n---\n").problems == [(3, "duplicate key 'name'")]
    unclosed = helper.parse("---\nname: a\n")
    assert unclosed.present and not unclosed.closed
    assert not helper.parse("# no front matter\n").present
    assert helper.parse("").fields == {}


def test_encode_and_quoted_phrases():
    assert helper.encode_double('a "b"\\c\n d') == '"a \\"b\\"\\\\c d"'
    value, ok = helper.decode_double(helper.encode_double('Say "hi"'))
    assert ok and value == 'Say "hi"'
    assert helper.quoted_phrases('Use when asked "is it safe?" or \u201cplease check\u201d') == [
        "is it safe?",
        "please check",
    ]


def test_find_skill_files(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "SKILL.md").write_text("x", encoding="utf-8")
    (tmp_path / "node_modules" / "b").mkdir(parents=True)
    (tmp_path / "node_modules" / "b" / "SKILL.md").write_text("x", encoding="utf-8")
    assert helper.find_skill_files([tmp_path]) == [tmp_path / "a" / "SKILL.md"]
    assert helper.find_skill_files([tmp_path / "a"]) == [tmp_path / "a" / "SKILL.md"]
