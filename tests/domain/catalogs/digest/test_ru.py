"""Русский каталог кластера выжимки следа: он надстройка над английским.

Мера тут одна - подстановки. Разошедшееся имя значения роняет ``cast log`` на
``KeyError`` уже у человека, и увидеть это можно только сверкой двух каталогов.
"""

from __future__ import annotations

import re
from string import Formatter

from torrcast.domain.catalogs.digest.en import en as english
from torrcast.domain.catalogs.digest.ru import ru as russian

#: Подстановки и спецификаторы формата: букв надписи в них нет.
_WORDS = re.compile(r"\{[^{}]*\}")


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


def test_no_russian_line_with_words_repeats_the_english_one() -> None:
    """Строка со словами, совпавшая с английской, - забытый перевод, а не совпадение.

    Совпадать позволено только голой рамке (``{stamp}{head}: {why}``): своих букв у
    неё нет, и переводить в ней нечего.
    """
    same = sorted(
        key
        for key, line in russian().items()
        if line == english()[key] and any(ch.isalpha() for ch in _WORDS.sub("", line))
    )
    assert same == []
