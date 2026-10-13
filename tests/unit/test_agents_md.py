"""AGENTS.md is the whole policy for a remote agent, so its text is checked like code."""

from __future__ import annotations

import re
from pathlib import Path

_PASTED_LINE_NUMBER = re.compile(r"^\s*\d+\|", re.M)
_INDEX_COUNTS = re.compile(r"^(\d+) commands, (\d+) modules, (\d+) public symbols\.$", re.M)
_COUNT_CLAIM = re.compile(
    r"(\d+)\s+(commands|comandos|modules|módulos|public symbols|símbolos públicos)\b"
)
_KIND = {
    "commands": "commands",
    "comandos": "commands",
    "modules": "modules",
    "módulos": "modules",
    "public symbols": "symbols",
    "símbolos públicos": "symbols",
}
# Short lines ("- HITL.") legitimately repeat; a pasted paragraph does not.
_MIN_REPEATED_LENGTH = 60


def _prose_lines(text: str) -> list[str]:
    lines: list[str] = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            lines.append(line.strip())
    return lines


def _pasted_line_numbers(text: str) -> list[str]:
    return [m.group(0).strip() for m in _PASTED_LINE_NUMBER.finditer(text)]


def _repeated_prose(text: str) -> list[str]:
    seen: set[str] = set()
    repeated: list[str] = []
    for line in _prose_lines(text):
        if len(line) < _MIN_REPEATED_LENGTH:
            continue
        if line in seen and line not in repeated:
            repeated.append(line)
        seen.add(line)
    return repeated


def _stale_counts(text: str, index: str) -> list[str]:
    match = _INDEX_COUNTS.search(index)
    assert match, "docs/capabilities.md lost its counts line"
    actual = {"commands": int(match[1]), "modules": int(match[2]), "symbols": int(match[3])}
    return [
        f"{number} {kind} (index: {actual[_KIND[kind]]})"
        for number, kind in _COUNT_CLAIM.findall(text)
        if int(number) != actual[_KIND[kind]]
    ]


def _agents(project_root: Path) -> str:
    return (project_root / "AGENTS.md").read_text(encoding="utf-8")


def test_no_line_numbers_pasted_from_a_file_viewer(project_root: Path) -> None:
    assert _pasted_line_numbers(_agents(project_root)) == []


def test_no_paragraph_is_pasted_twice(project_root: Path) -> None:
    assert _repeated_prose(_agents(project_root)) == []


def test_counts_quoted_from_the_index_are_current(project_root: Path) -> None:
    index = (project_root / "docs" / "capabilities.md").read_text(encoding="utf-8")
    assert _stale_counts(_agents(project_root), index) == []


def test_the_checks_catch_what_they_exist_for() -> None:
    paragraph = "Job descriptions are pulled from **Indeed** (`jobs search`), **LinkedIn** posts"
    pasted = (
        f"{paragraph}\n"
        f"{paragraph}\n"
        "    90|(`linkedin sweep`), or a **hard link**\n"
        "```text\n"
        "jobbot cv advise --job J0001 # scope a un aviso, repetido dentro de un bloque de código\n"
        "jobbot cv advise --job J0001 # scope a un aviso, repetido dentro de un bloque de código\n"
        "```\n"
        "Read the index: 99 modules and 491 public symbols.\n"
    )
    index = "113 commands, 161 modules, 837 public symbols.\n"

    assert _pasted_line_numbers(pasted) == ["90|"]
    assert _repeated_prose(pasted) == [paragraph]
    assert _stale_counts(pasted, index) == [
        "99 modules (index: 161)",
        "491 public symbols (index: 837)",
    ]
