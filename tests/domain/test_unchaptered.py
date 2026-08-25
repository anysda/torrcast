"""Зеркало :mod:`torrcast.domain.unchaptered`: «часть N» - не номер в линейке франшизы."""

from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.unchaptered import _unchaptered


def _picture(part: int, release_title: str) -> Picture:
    return Picture(
        title="Гарри Поттер",
        year=2000 + part,
        part=part,
        releases=[Release(raw_name=release_title, title=release_title)],
    )


def test_a_picture_cut_into_named_chapters_loses_its_part_number() -> None:
    """Одно кино, выложенное двумя частями, - это не две части франшизы."""
    found = _unchaptered(
        [_picture(1, "Гарри Поттер: Часть 1"), _picture(2, "Гарри Поттер: Часть 2")]
    )

    assert [p.part for p in found] == [None, None]


def test_a_franchise_of_real_parts_keeps_its_numbers() -> None:
    """Без первой названной части резать нечего: номера тут настоящие."""
    found = _unchaptered([_picture(1, "Брат"), _picture(2, "Брат 2")])

    assert [p.part for p in found] == [1, 2]
