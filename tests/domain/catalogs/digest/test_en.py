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


def test_the_stamp_keeps_its_width() -> None:
    """Отметка времени держит ширину поля: строки выжимки идут столбиком.

    Ширина живёт в каталоге, а не в коде (:func:`torrcast.domain.digest._event_line`),
    и потерянный ``:6.1f`` разъехал бы всю ленту, ничего при этом не уронив.
    """
    assert english()["digest.stamp"] == "+{at:6.1f}s "
