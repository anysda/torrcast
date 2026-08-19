"""Поля клиента одного поиска: остаток цели, потолок следующего круга и его пол."""

from __future__ import annotations

import time

from torrcast.adapters.prowlarr.prowlarr_state import _State
from torrcast.domain.goal_spare import CIRCLE_SHARE


def _client() -> _State:
    return _State("http://prowlarr.invalid", "ключ")


def test_the_goal_left_is_counted_from_the_start_of_the_search() -> None:
    """Клиент живёт ровно один поиск, поэтому «создан» и «начат» тут одно и то же (TC-228)."""
    client = _client()

    assert client.spare() > 0.0, "только что начатому поиску цель ещё не съели"
    client._began = time.monotonic() - 30.0

    assert client.spare() == 0.0, "цели не осталось вовсе"


def test_a_circle_asked_for_less_than_its_floor_is_a_guaranteed_silent_one() -> None:
    """🔴 TC-386. Круг с нулевым бюджетом - не экономия, а лишний запрос к трекеру."""
    client = _client()
    client._began = time.monotonic() - 30.0

    assert client.circle_cap() == CIRCLE_SHARE, "пол по умолчанию - доля круга"
    client.cap_floor = 10.0  # так делает добор по второму имени картины

    assert client.circle_cap() == 10.0, "добор поднимает пол до целой цели"
