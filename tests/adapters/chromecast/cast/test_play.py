"""Начало показа: LOAD с позицией, ожидание картинки и честная смерть вместо молчания."""

from __future__ import annotations

from typing import Any

import pytest

from tests.adapters.chromecast.cast.wired import Wired
from torrcast.adapters.chromecast.cast.play import _play
from torrcast.domain.start_refused_error import StartRefusedError


class _Quiet(Wired):
    """Приёмник без сети: LOAD и ожидание картинки - записи, а не разговор с ТВ."""

    def __init__(self, settles: bool = True, **rest: Any) -> None:
        super().__init__(**rest)
        self.settles = settles
        self.loads: list[float] = []
        self.budgets: list[float] = []

    def _load(self, at: float = 0.0, paused: bool = False) -> None:
        self.loads.append(at)

    def _settle(self, budget: float) -> bool:
        self.budgets.append(budget)
        return self.settles

    def _why(self) -> str:
        return "IDLE/ERROR"


def test_the_show_waits_for_a_picture_and_not_for_a_sent_command() -> None:
    """Без ожидания показ гаснет через секунду: сторож видит закономерный IDLE.

    ``at`` - это resume: манифест описывает весь фильм, поэтому продолжение с середины
    делается обычным LOAD с позицией, а не перепаковкой «с нуля потока».
    """
    receiver = _Quiet()

    _play(receiver, "http://дом/поток.m3u8", "Моана", at=1272.4)

    assert receiver.loads == [1272.4]
    assert receiver.budgets == [receiver.START_TIMEOUT]
    assert receiver._url == "http://дом/поток.m3u8"
    assert receiver._title == "Моана"


def test_a_show_without_a_title_still_has_one_on_the_screen() -> None:
    """Пустое имя на экране приёмника выглядело бы поломкой, а не пустотой."""
    receiver = _Quiet()

    _play(receiver, "http://дом/поток.m3u8")

    assert receiver._title == "torrcast"


def test_a_second_show_gets_the_revive_patience_and_a_clean_count_of_deaths() -> None:
    """Приёмник один на весь юнит, а сетка у каждой серии своя.

    Унаследуй следующая серия смерти прошлой - её первый же спотык считался бы третьим,
    и показ перешагивал бы здоровый кусок.
    """
    receiver = _Quiet()
    _play(receiver, "http://дом/первая.m3u8")
    receiver._deaths[137.0] = 2

    _play(receiver, "http://дом/вторая.m3u8")

    assert receiver._deaths == {}
    assert receiver.budgets[-1] == receiver.profile.revive_timeout


def test_a_refused_load_is_the_first_death_and_not_the_end_of_the_show() -> None:
    """Приёмник в сети, и поднимать его есть чем: хоронить показ здесь нельзя.

    Иначе зритель остаётся перед чёрным экраном при живом телевизоре.
    """
    receiver = _Quiet(settles=False)

    with pytest.raises(StartRefusedError, match="не начал показ: IDLE/ERROR"):
        _play(receiver, "http://дом/поток.m3u8")


def test_the_watchdog_starts_the_show_from_a_clean_slate() -> None:
    """Счётчики подвиса и перемотки прошлого показа к новому отношения не имеют."""
    receiver = _Quiet()
    receiver._blind, receiver._gone, receiver._stall_hits = 3, True, 5
    receiver._nudged_to, receiver._seen = 900.0, 800.0

    _play(receiver, "http://дом/поток.m3u8", at=10.0)

    assert (receiver._blind, receiver._gone, receiver._stall_hits) == (0, False, 0)
    assert (receiver._nudged_to, receiver._seen) == (-1.0, -1.0)
    assert receiver._peak == 10.0
