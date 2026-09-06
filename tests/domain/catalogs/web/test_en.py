"""Английский каталог страницы: он же умолчание, он же запасной.

Кириллица в нём - не опечатка, а невыполненный перевод: запасной каталог отвечает всем,
у кого языка нет вовсе, и русская строка оттуда уехала бы англоязычному человеку.
"""

from __future__ import annotations

import re

from torrcast.domain.catalogs.web.en import en as english

_CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def test_english_catalog_holds_no_russian() -> None:
    russian = [key for key, line in english().items() if _CYRILLIC.search(line)]
    assert russian == []


def test_every_key_names_its_cluster() -> None:
    stray = [key for key in english() if not key.startswith("web.")]
    assert stray == []


def test_no_line_is_shouted_in_the_catalog() -> None:
    """Прописные буквы витрины делает стиль, а не каталог: иначе перевод их унаследует."""
    shouted = [
        key
        for key, line in english().items()
        if line.upper() == line
        and any(letter.isalpha() for letter in line)
        and key not in {"web.player.volume", "web.player.tv_volume"}
    ]
    assert shouted == []
