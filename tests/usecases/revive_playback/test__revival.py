"""Зеркало лестницы подъёма: темнота меряется часами, а запас попыток - прожитой картинкой."""

from __future__ import annotations

from tests.fakes.clock import FakeClock
from torrcast.usecases.revive_playback._revival import _Revival


def test_the_darkness_is_counted_from_its_own_start() -> None:
    """Сколько темно - это часы лестницы, а не догадка: без темноты тут ноль."""
    clock = FakeClock(now=100.0)
    revival = _Revival(clock=clock)

    assert revival.darkness() == 0.0

    revival.since, revival.why = 90.0, "сети нет"  # метка темноты - причина, не часы

    assert revival.darkness() == 10.0


def test_a_live_picture_ends_the_darkness_and_wipes_its_marks() -> None:
    """Показ пошёл - темноты нет ни в одном её признаке, включая метку для чужого процесса."""
    clock = FakeClock(now=200.0)
    revival = _Revival(clock=clock, since=100.0, began=1.0, why="сети нет", blamed=True)

    revival.alive()

    assert (revival.since, revival.began, revival.why) == (0.0, 0.0, "")
    assert (revival.blamed, revival.dropped) == (False, False)
    assert revival.back == 200.0, "с этого мгновения считается прожитая картинка"


def test_the_spent_tries_come_back_only_with_a_lived_minute() -> None:
    """Подъём запаса не возвращает - его возвращает картинка, которая идёт и не гаснет."""
    clock = FakeClock(now=1000.0)
    revival = _Revival(clock=clock, tries=2, lived=60.0, since=900.0, why="сети нет")
    revival.alive()  # темнота кончилась, отсчёт прожитого пошёл

    clock.now = 1059.0
    revival.alive()

    assert revival.tries == 2, "минуту ещё не прожили - запас возвращать не за что"

    clock.now = 1060.0
    revival.alive()

    assert (revival.tries, revival.back) == (0, 0.0)


def test_buffering_restarts_the_lived_minute() -> None:
    """``BUFFERING`` - не картинка: доказательство пережитого обрыва считается заново."""
    clock = FakeClock(now=1000.0)
    revival = _Revival(clock=clock, tries=1, lived=60.0, since=900.0, why="сети нет")
    revival.alive()

    clock.now = 1059.0
    revival.alive(shown=False)  # встала картинка
    clock.now = 1118.0
    revival.alive()

    assert revival.tries == 1, "минуту считают от последнего кадра, а не от подъёма"

    clock.now = 1119.0
    revival.alive()

    assert revival.tries == 0
