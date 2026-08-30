"""Зеркало подстановки надписей: язык, запасной каталог и ключи, которых нет.

Отдельно тут сторож ключей: каждый ключ, названный в исходниках продукта, обязан
существовать в каталоге. Опечатка в ключе иначе доезжает до человека ``KeyError``-ом
на середине показа, и ни один тест кластера её не видит.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

from torrcast.domain.catalogs.choice.en import en as english
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.catalogs.tongue import _choose_tongue, tongue

_ROOT = Path(__file__).parents[3]


@pytest.fixture(autouse=True)
def _restore() -> Iterator[None]:
    was = tongue()
    yield
    _choose_tongue(was)


def _keys_named_in_sources() -> set[str]:
    found: set[str] = set()
    for path in sorted((_ROOT / "torrcast").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "phrase" or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.add(first.value)
    return found


def test_english_answers_by_default() -> None:
    _choose_tongue("en")
    assert phrase("choice.question") == "What are we watching?"


def test_russian_answers_when_chosen() -> None:
    _choose_tongue("ru")
    assert phrase("choice.question") == "Что смотрим?"


def test_values_are_substituted_by_name() -> None:
    _choose_tongue("en")
    assert phrase("choice.default", picture="Dune (2021)", number=2, total=7) == (
        "Enter - “Dune (2021)”, item 2 of 7"
    )


def test_unknown_key_falls_out_loud() -> None:
    with pytest.raises(KeyError):
        phrase("choice.no_such_line")


def test_every_key_named_in_sources_exists() -> None:
    missing = sorted(_keys_named_in_sources() - set(english()))
    assert missing == []
