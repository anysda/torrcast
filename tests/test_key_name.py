"""Имя картины, восстановленное из ключа: последний довод прямой ссылки."""

from __future__ import annotations

import pytest

from torrcast.domain.kind import Kind
from torrcast.domain.picture import Picture
from web.key_name import key_name


@pytest.mark.parametrize(
    ("title", "year", "kind"),
    [
        ("Матрица", 1999, "movie"),
        ("Интерстеллар", 2014, "movie"),
        ("Укрытие", 2023, "tv"),
    ],
)
def test_the_name_comes_back_out_of_the_key_the_picture_built(
    title: str, year: int, kind: Kind
) -> None:
    """Ключ собирает :attr:`Picture.key`, и имя обязано вернуться из него, а не из догадки."""
    assert key_name(Picture(title=title, year=year, kind=kind).key) == title.lower()


def test_a_name_of_several_words_comes_back_with_its_spaces() -> None:
    """Слова в ключе разделены дефисом, и круг должен получить их пробелами."""
    assert key_name("movie:матрица-перезагрузка:2003") == "матрица перезагрузка"


@pytest.mark.parametrize("key", ["", "movie::2014", "::", "movie:"])
def test_a_key_without_a_name_says_so_with_an_empty_string(key: str) -> None:
    """Пустая строка - это «спрашивать нечем»: на ней :func:`web.card.card` отказывает."""
    assert key_name(key) == ""
