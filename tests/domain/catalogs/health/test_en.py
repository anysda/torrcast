"""Английский каталог кластера самопроверки: он же умолчание, он же запасной.

Кириллица в нём - не опечатка, а невыполненный перевод: запасной каталог отвечает всем,
у кого языка нет вовсе, и русская строка оттуда уехала бы англоязычному человеку.
"""

from __future__ import annotations

import re

from torrcast.domain.catalogs.health.en import en as english

_CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def test_english_catalog_holds_no_russian() -> None:
    russian = [key for key, line in english().items() if _CYRILLIC.search(line)]
    assert russian == []


def test_every_key_names_its_cluster() -> None:
    stray = [key for key in english() if not key.startswith("health.")]
    assert stray == []
    assert english()["health.link_wifi"] == "over Wi-Fi"


def test_the_three_verdicts_stand_in_one_column() -> None:
    """Оценка слева добивается пробелами до общей ширины: строки идут столбиком.

    Ширина эта у каждого языка своя, и держит её каталог, а не код
    (:class:`torrcast.domain.health_verdict.HealthVerdict`). Разъехавшийся столбик -
    не косметика: ``cast doctor`` читают глазами сверху вниз.
    """
    heads = [
        english()[key].removesuffix("{text}") for key in ("health.ok", "health.warn", "health.bad")
    ]
    assert len({len(head) for head in heads}) == 1, heads
