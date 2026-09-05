"""Круг опроса: срок между кругами, отметка закладки и рассказ об отказе."""

from __future__ import annotations

from datetime import timedelta
from itertools import pairwise
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.torrcast.const import SCAN_INTERVAL_SHOWING
from tests.hass_integration.conftest import BASE, CLOCK, PLAYER, snapshot
from tests.hass_integration.helpers import added, drawn, polled_again


async def test_the_same_failure_is_told_once(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """Один и тот же `last_error` показывается один раз, а не на каждом опросе."""
    entry = await added(hass, aioclient_mock, snapshot(last_error=None))
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/api/state", json=snapshot(last_error="торрент не открылся"))
    told = "custom_components.torrcast.coordinator.persistent_notification.async_create"
    with patch(told) as notice:
        await entry.runtime_data.async_refresh()
        await entry.runtime_data.async_refresh()
    assert notice.call_count == 1
    assert notice.call_args.args[1] == "торрент не открылся"
    assert hass.states.get(PLAYER).attributes["last_error"] == "торрент не открылся"


async def test_a_bookmark_that_stood_still_does_not_throw_the_slider_back(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """🔴 TC-1019. Ползунок идущего показа не откатывается назад.

    Показ кладёт закладку в запись раз в десять секунд, а карточка спрашивает раз в
    пять: на каждом втором ответе место ТО ЖЕ. Метка, которую двигал сам факт ответа,
    делала из этого пилу - ползунок уезжал на круг опроса вперёд и падал обратно,
    и так весь показ (замер на стенде: откат 4,0 с каждые десять секунд).
    """
    entry = await added(hass, aioclient_mock, snapshot(state="playing", position=294.2))
    later = dt_util.utcnow() + SCAN_INTERVAL_SHOWING
    moment = later + timedelta(seconds=1)
    before = drawn(hass, moment)

    with patch(f"{CLOCK}.utcnow", return_value=later):
        await polled_again(hass, aioclient_mock, entry, state="playing", position=294.2)

    after = drawn(hass, moment)
    assert after >= before, f"ползунок откатился на {before - after:.1f} с"


async def test_a_bookmark_that_moved_takes_the_slider_with_it(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Метка стоит на месте не сама по себе, а вместе с закладкой.

    Замерший навсегда отсчёт прошёл бы проверку на пилу так же гладко, как правка, - и
    ползунок уехал бы в бесконечность. Двинулась закладка - двигается и ползунок.
    """
    entry = await added(hass, aioclient_mock, snapshot(state="playing", position=294.2))
    later = dt_util.utcnow() + SCAN_INTERVAL_SHOWING
    moment = later + timedelta(seconds=1)
    before = drawn(hass, moment)

    with patch(f"{CLOCK}.utcnow", return_value=later):
        await polled_again(hass, aioclient_mock, entry, state="playing", position=304.4)

    assert drawn(hass, moment) > before, "новое место закладки не сдвинуло ползунок"


async def test_a_seek_backwards_puts_the_slider_where_it_was_dropped(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Перемотка назад ставит ползунок туда, куда его отпустили (TC-1014 не потерять).

    Место уехало назад - прежнему отсчёту верить нечему: он про другую точку картины.
    """
    entry = await added(hass, aioclient_mock, snapshot(state="playing", position=294.2))

    await polled_again(hass, aioclient_mock, entry, state="playing", position=60.0)

    landed = drawn(hass, dt_util.utcnow())
    assert 60.0 <= landed < 61.0, f"ползунок после перемотки назад оказался на {landed:.1f}"


async def test_a_bookmark_that_gained_less_than_the_wall_clock_does_not_throw_it_back(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """🔴 TC-1019. Показанное человеку не ходит назад НИКОГДА, кроме его же перемотки.

    Живой замер 03-09-2026: закладка шла шагом 10 с, 11 с и 4 с за 8 с настенного
    времени, и на последнем шаге счётчик времени на карточке откатился на 1,3 с. Пол,
    к которому подтягивали отсчёт, ровно это и делал: показ, отставший от настенных
    часов, отставал и от пола, а подтяжка вычитала отставание из числа перед глазами.
    """
    entry = await added(hass, aioclient_mock, snapshot(state="playing", position=2471.0))
    start = dt_util.utcnow()
    shown = [drawn(hass, start)]

    # Закладка стоит два круга опроса, а потом двигается меньше, чем прошло времени.
    for passed, place in ((5.0, 2471.0), (10.0, 2471.0), (15.0, 2475.0), (20.0, 2480.0)):
        moment = start + timedelta(seconds=passed)
        with patch(f"{CLOCK}.utcnow", return_value=moment):
            await polled_again(hass, aioclient_mock, entry, state="playing", position=place)
        shown.append(drawn(hass, moment))

    falls = [round(before - after, 1) for before, after in pairwise(shown) if after < before]
    assert not falls, f"ползунок откатился назад на {falls}; показанное подряд: {shown}"


async def test_a_show_that_is_not_playing_puts_the_slider_on_the_bookmark_itself(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Отставание отсчёта отдаётся обратно на всяком состоянии, кроме идущего показа.

    Карточка не идущего показа не тикает, поэтому падать тут нечему, - а без этого
    отставание, набранное на застрявшем приёмнике, жило бы до конца сеанса.
    """
    entry = await added(hass, aioclient_mock, snapshot(state="playing", position=2471.0))
    later = dt_util.utcnow() + timedelta(seconds=30)

    with patch(f"{CLOCK}.utcnow", return_value=later):
        await polled_again(hass, aioclient_mock, entry, state="paused", position=2475.0)

    landed = drawn(hass, later)
    assert 2475.0 <= landed < 2476.0, f"ползунок вставшего показа оказался на {landed:.1f}"
