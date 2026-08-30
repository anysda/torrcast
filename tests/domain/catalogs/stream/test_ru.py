"""Русский каталог кластера картинки и звука: он надстройка над английским.

Мера тут одна - подстановки. Разошедшееся имя значения роняет строку на ``KeyError``
уже у человека, и увидеть это можно только сверкой двух каталогов.
"""

from __future__ import annotations

from string import Formatter

from torrcast.domain.catalogs.stream.en import en as english
from torrcast.domain.catalogs.stream.ru import ru as russian


def _values(line: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(line) if name}


def test_russian_names_no_key_the_english_does_not_know() -> None:
    stray = sorted(set(russian()) - set(english()))
    assert stray == []


def test_both_tongues_ask_for_the_same_values() -> None:
    apart = {
        key: (_values(english()[key]), _values(line))
        for key, line in russian().items()
        if _values(english()[key]) != _values(line)
    }
    assert apart == {}


def test_no_russian_line_repeats_the_english_one() -> None:
    """Строка, совпавшая с английской, - забытый перевод, а не совпадение.

    Голых рамок без единого слова в этом кластере нет, поэтому совпадение тут значит
    ровно одно: ключ не переведён.
    """
    same = sorted(key for key, line in russian().items() if line == english()[key])
    assert same == []
