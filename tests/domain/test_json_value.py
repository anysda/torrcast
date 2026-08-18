"""Зеркало :mod:`torrcast.domain.json_value`: имя разобранного JSON обязано покрывать его весь.

Мера тут одна и она про смысл имени: всё, во что :mod:`json` разбирает документ, обязано
быть НАЗВАНО в псевдониме. Пропусти он хоть одну ветку - и договор снова начал бы врать:
читатель объявил бы «у меня разобранный JSON», а половина значений в это имя не влезала бы.
"""

from __future__ import annotations

import json
from typing import get_args, get_origin

from torrcast.domain.json_value import JsonValue

#: Документ со ВСЕМИ ветками разбора: строка, целое, дробное, оба булевых, пусто, массив,
#: объект - и вложенность, ради которой псевдоним и сделан рекурсивным.
DOCUMENT = (
    '{"s": "x", "i": 1, "f": 1.5, "yes": true, "no": false, "n": null, "a": [[1]], "o": {"k": {}}}'
)


def _named() -> set[type]:
    """Типы, названные в псевдониме: у обобщённых берётся сам контейнер."""
    return {get_origin(part) or part for part in get_args(JsonValue)}


def _shapes(value: JsonValue) -> set[type]:
    """Типы всех узлов документа, включая вложенные."""
    found = {type(value)}
    if isinstance(value, dict):
        for inner in value.values():
            found |= _shapes(inner)
    elif isinstance(value, list):
        for inner in value:
            found |= _shapes(inner)
    return found


def test_the_alias_names_every_shape_json_parses_into() -> None:
    """Ни один узел разобранного документа не остаётся без имени в псевдониме."""
    parsed: JsonValue = json.loads(DOCUMENT)

    assert _shapes(parsed) <= _named()


def test_the_alias_names_nothing_json_never_parses_into() -> None:
    """И наоборот: лишних имён в нём нет - псевдоним описывает JSON, а не «что угодно».

    Заведись в нём ``object`` - имя перестало бы что-либо обещать, а именно за этим оно и
    заведено.
    """
    assert _named() == {str, int, float, bool, type(None), list, dict}
