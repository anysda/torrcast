"""Зеркало отказа: франшиза без нужного номера и «ничего не нашлось» - строки разные."""

from __future__ import annotations

import pytest

from tests.usecases.discover.world import pictures, row
from torrcast.usecases.discover._nothing import _nothing


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русские строки отказа по франшизе и по пустому поиску."""


_CARS = pictures(
    [
        row("Тачки / Cars (2006) BDRip 1080p", "a"),
        row("Тачки 2 / Cars 2 (2011) BDRip 1080p", "b"),
    ]
)


def test_a_living_franchise_without_the_asked_number_lists_what_it_has() -> None:
    """🔴 TC-373. Молчаливого отказа не бывает: строка называет счёт франшизы и её части."""
    line = _nothing("тачки", 9, _CARS)

    assert "картин во франшизе 2" in line
    assert "номера 9 нет" in line
    assert "Тачки (2006)" in line and "Тачки 2 (2011)" in line


def test_without_a_number_the_refusal_is_the_honest_one() -> None:
    """Номера не спрашивали - про франшизу говорить нечего, и строка про сам запрос."""
    assert _nothing("дети мужчин", None, _CARS) == "по запросу «дети мужчин» ничего не нашлось"


def test_a_number_without_a_franchise_behind_it_is_the_same_honest_refusal() -> None:
    """Номер назван, а франшизы под ним нет - отправлять проверять номер было бы враньём."""
    assert _nothing("дети мужчин", 2, _CARS) == "по запросу «дети мужчин» ничего не нашлось"
