"""Проверяет shelf_seeds: о каких картинах полка вообще спрашивает обложку."""

from __future__ import annotations

from torrcast.domain.picture import Picture
from web.shelf_seeds import shelf_seeds


def _mixed() -> list[Picture]:
    return [Picture(title="Latin", year=2001), Picture(title="Картина", year=2002)]


def _titles(pictures: list[Picture]) -> list[str]:
    return [str(seed["title"]) for seed in shelf_seeds(pictures) if isinstance(seed, dict)]


def test_under_russian_a_picture_without_a_russian_name_is_not_a_seed(
    _russian_product: None,
) -> None:
    """Латинское имя под русским не зовётся: такой записи и обложку не ищут."""
    assert _titles(_mixed()) == ["Картина"]


def test_under_english_every_picture_is_a_seed(_english: None) -> None:
    """Под английским латиница и есть имя показа: отсева нет."""
    assert _titles(_mixed()) == ["Latin", "Картина"]
