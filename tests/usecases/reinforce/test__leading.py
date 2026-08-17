"""Вожак выдачи: самая полная картина, на которую и смотрит гейт добора."""

from __future__ import annotations

from tests.usecases.reinforce.stand import releases, row
from torrcast.domain.picture import Picture
from torrcast.usecases.reinforce._leading import _leading


def _picture(title: str, year: int, rows: int) -> Picture:
    """Картина ровно с тем числом раздач, которым вожак и меряется."""
    return Picture(
        title=title,
        year=year,
        releases=releases(
            [row(f"{title} / X ({year}) BDRip 1080p", chr(97 + n)) for n in range(rows)]
        ),
    )


def test_the_fullest_picture_leads() -> None:
    """Дефолт меню и тот, кто сыграет без терминала, - это она же."""
    thin, fat = _picture("Тачки", 2006, 2), _picture("Тачки 3", 2017, 5)

    assert _leading([thin, fat]) is fat


def test_nobody_leads_an_empty_pool() -> None:
    """Пустая выдача вожака не назначает: сверять добору будет не с чем."""
    assert _leading([]) is None


def test_the_first_of_the_equals_stays_the_leader() -> None:
    """Раздач поровну - вожак прежний: перетасовка меню от одного вопроса недопустима."""
    first, second = _picture("Тачки", 2006, 3), _picture("Тачки 2", 2011, 3)

    assert _leading([first, second]) is first
