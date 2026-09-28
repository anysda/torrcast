"""Английский каталог страницы: он же умолчание, он же запасной.

Кириллица в нём - не опечатка, а невыполненный перевод: запасной каталог отвечает всем,
у кого языка нет вовсе, и русская строка оттуда уехала бы англоязычному человеку.
"""

from __future__ import annotations

import re
from pathlib import Path

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


def test_page_javascript_has_no_russian_string_literals() -> None:
    """Comments may be Russian, but every string the page can show is catalogued."""
    root = Path(__file__).parents[4] / "web" / "static"
    # One left-to-right pass: whichever starts first wins, so ``//`` inside a string stays
    # a string and a quote inside a comment stays a comment. Template literals count too.
    token = re.compile(
        r"//[^\n]*|/\*.*?\*/"
        r"|(?P<text>'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"|`(?:[^`\\]|\\.)*`)",
        re.DOTALL,
    )
    cyrillic = re.compile(r"[А-Яа-яЁё]")
    offenders = [
        f"{path.name}: {match.group('text')}"
        for path in sorted(root.glob("*.js"))
        for match in token.finditer(path.read_text(encoding="utf-8"))
        if match.group("text") and cyrillic.search(match.group("text"))
    ]
    assert offenders == []
