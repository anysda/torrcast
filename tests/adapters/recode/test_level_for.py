"""Уровень H.264: обещание декодеру считается от кадра, а не пишется строкой."""

from __future__ import annotations

import pytest

from torrcast.adapters.recode.level_for import level_for


@pytest.mark.parametrize(
    ("frame", "level"),
    [(0, "4.1"), (720, "4.1"), (1080, "4.1"), (1440, "5.0"), (2160, "5.1"), (4320, "6.0")],
)
def test_the_level_grows_with_the_frame(frame: int, level: str) -> None:
    """1080p - это 8160 макроблоков при потолке 4.1 в 8192; 2160p - 32400, вчетверо выше.

    Прибитая строка «4.1» на 4К обещала декодеру кадр вчетверо меньше того, что лежит в
    потоке (TC-224).
    """
    assert level_for(frame) == level


def test_the_level_never_shrinks_as_the_frame_grows() -> None:
    """Уровень - потолок: занижать нельзя, декодер вправе не начать показ."""
    ladder = [level_for(frame) for frame in (0, 360, 720, 1080, 1440, 2160, 4320, 8640)]
    assert ladder == sorted(ladder, key=float), "уровень обязан только расти"
    assert level_for(10_000) == "6.0", "выше таблицы отдаём её верх, а не срываемся"
