"""Верить ли карте опорных кадров на этом файле: по умолчанию да, и это решение TC-133."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from torrcast.adapters.pack_memory import _MAP_LIED
from torrcast.adapters.stream_pack.map_lied import map_lied
from torrcast.adapters.stream_pack.map_trusted import map_trusted

URL = "http://торрент/поток?link=раздача"


@pytest.fixture(autouse=True)
def _own_memory() -> Iterator[None]:
    """Снятое доверие помнится на весь процесс; каждой пробе оно достаётся нетронутым."""
    _MAP_LIED.clear()
    yield
    _MAP_LIED.clear()


def test_a_file_nobody_complained_about_is_trusted_at_once() -> None:
    """🔴 Пустая память значит «верим», а не «ещё не проверяли».

    Прежде было наоборот: карте не верили, пока её не подтвердит пробный прогон, и прогон
    этот стоял ровно на пути к первой картинке (замер репы: 0.029 с на файле в tmpfs,
    0.042 с по http на петле, против 1.6-10.9 мкс у самой карты). Перевернуть умолчание
    и было правкой; сверка переехала на факт нарезки.
    """
    assert map_trusted(URL) is True


def test_a_file_whose_map_lied_is_never_trusted_again() -> None:
    """Снятое доверие держится до конца процесса: карта врёт про файл, а не про заход."""
    map_lied(URL)

    assert map_trusted(URL) is False
    assert map_trusted(URL) is False, "доверие вернулось само: приговор оказался разовым"


def test_the_verdict_covers_the_named_file_and_not_the_shelf() -> None:
    """Ключ - URL потока, тот же, что у кэша карты: соседняя раздача остаётся доверенной."""
    map_lied(URL)

    assert map_trusted("http://торрент/поток?link=соседняя") is True
