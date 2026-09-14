"""Сторож шага, которым вкладка и ТВ-страница ждут ящик показа."""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "web" / "static"


def _number(name: str) -> int:
    found = re.search(rf"^\s*{name}: (\d+),$", (STATIC / "player-box.js").read_text("utf-8"), re.M)
    assert found, f"в player-box.js нет {name}"
    return int(found.group(1))


def test_the_empty_box_is_asked_often_at_first_and_only_for_a_bounded_time() -> None:
    """Секунда шага доплачивала до секунды к старту; частый шаг обязан кончаться сам.

    Ящик спрашивает и ТВ-страница тем же циклом, поэтому потолок - число запросов на заказ.
    """
    fast, fast_for, slow = _number("FAST_MS"), _number("FAST_FOR_MS"), _number("SLOW_MS")
    assert fast <= 250, f"шаг {fast} мс: страница узнаёт о ящике на {fast} мс позже показа"
    assert fast_for // fast <= 150, "частый опрос без потолка грузит мост"
    assert slow == 1000


def test_the_player_waits_the_box_with_this_pace_and_not_a_fixed_second() -> None:
    """Цикл ожидания ящика берёт шаг у ``pace``, а не зашитую секунду."""
    live = (
        (STATIC / "player.js").read_text("utf-8").split("async _live()", 1)[1].split("\n  },", 1)[0]
    )
    assert "TCPlayer._sleep(TCPlayerBox.pace(Date.now() - began))" in live
    assert "_sleep(1000)" not in live
