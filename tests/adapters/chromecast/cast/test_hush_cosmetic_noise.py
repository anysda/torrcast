"""Приглушение косметической жалобы: идемпотентно и без вреда настоящим жалобам."""

from __future__ import annotations

import logging

import pytest

from torrcast.adapters.chromecast.cast.cosmetic import _DIAL_LOGGER, _Cosmetic
from torrcast.adapters.chromecast.cast.hush_cosmetic_noise import hush_cosmetic_noise


@pytest.fixture
def logger(monkeypatch: pytest.MonkeyPatch) -> logging.Logger:
    """Логгер pychromecast со своим пустым списком фильтров на время теста."""
    found = logging.getLogger(_DIAL_LOGGER)
    monkeypatch.setattr(found, "filters", [])
    return found


def test_the_filter_is_hung_on_the_library_logger(logger: logging.Logger) -> None:
    """Фильтр вешается снаружи: сама pychromecast при этом не трогается."""
    hush_cosmetic_noise()

    assert any(isinstance(one, _Cosmetic) for one in logger.filters)


def test_calling_it_again_does_not_pile_up_filters(logger: logging.Logger) -> None:
    """Зовут её на каждом подключении и на каждом адресе обхода подсети.

    Не проверяй она себя - на обходе ``/24`` на логгер село бы 254 одинаковых фильтра,
    и каждая строка чужой библиотеки проходила бы их все подряд.
    """
    for _ in range(5):
        hush_cosmetic_noise()

    assert len([one for one in logger.filters if isinstance(one, _Cosmetic)]) == 1


def test_a_foreign_filter_next_to_ours_survives(logger: logging.Logger) -> None:
    """Чужой фильтр на том же логгере не снимается: он не наш, и трогать его нельзя."""
    alien = logging.Filter()
    logger.addFilter(alien)

    hush_cosmetic_noise()

    assert alien in logger.filters
