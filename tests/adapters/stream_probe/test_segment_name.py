"""Имя сегмента: место в фильме, а не номер по порядку упаковки."""

from __future__ import annotations

from torrcast.adapters.stream_probe.segment_name import segment_name


def test_the_name_is_the_place_in_the_film() -> None:
    """Ровно это и делает возможным манифест на весь фильм при упаковке по требованию.

    Будь имя номером по порядку упаковки, прогон со второй половины фильма выкладывал бы
    ``v0.ts`` поверх начала.
    """
    assert segment_name(0) == "v0.ts"
    assert segment_name(359) == "v359.ts"


def test_the_names_of_different_slots_never_collide() -> None:
    """Два прогона кладут куски в один каталог, и затирать чужой нельзя."""
    made = {segment_name(slot) for slot in range(500)}

    assert len(made) == 500
