"""Английский каталог кластера выжимки следа: он же умолчание, он же запасной.

Кириллица в нём - не опечатка, а невыполненный перевод: запасной каталог отвечает всем,
у кого языка нет вовсе, и русская строка оттуда уехала бы англоязычному человеку.
"""

from __future__ import annotations

import re

from torrcast.domain.catalogs.digest.en import en as english

_CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def test_english_catalog_holds_no_russian() -> None:
    russian = [key for key, line in english().items() if _CYRILLIC.search(line)]
    assert russian == []


def test_every_key_names_its_cluster() -> None:
    stray = [key for key in english() if not key.startswith("digest.")]
    assert stray == []
    assert english()["digest.plan_copy"] == "copy"


def test_no_line_carries_a_number_format_of_its_own() -> None:
    """Каталог принимает уже готовые слова: числа складывает в строку зовущий.

    Иначе надпись хранила бы ``:.1f`` и падала бы на всём, что не число, - а ключ
    каталога пришёл бы в показ ``ValueError``-ом посреди ленты. Ширина отметки времени
    живёт теперь рядом с местом, где она считается
    (:func:`torrcast.domain.digest._event_line`), и там же меряется столбиком.
    """
    spec = re.compile(r"\{\w+[:!][^{}]*\}")
    assert [key for key, line in english().items() if spec.search(line)] == []
