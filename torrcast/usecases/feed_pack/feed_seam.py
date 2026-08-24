"""Переход с прогретого на живую упаковку: поднять её до того, как прогретое кончится.

Зовут отсюда выдачу прогретого куска (:mod:`torrcast.usecases.feed_pack.feed_segment`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.feed_pack._state as _state
from torrcast.ports.journal.slot import journal
from torrcast.usecases.feed_pack.feed_segment import _have

if TYPE_CHECKING:
    from collections.abc import Callable

    from torrcast.usecases.feed_pack.feed_state import _State


def _seam(state: _State, slot: int, restart: Callable[[int], None]) -> None:
    """Прогретое впереди на исходе — начать паковать первое место ЗА его концом.

    🔴 Прогретое читается показом первым, и упаковку это не двигает вовсе: запрос на
    прогретый кусок отвечается файлом, не заглядывая в прогон
    (:func:`torrcast.usecases.feed_pack.feed_segment._segment`). Пока прогретое есть, так и
    надо. Но обеспечение показа кончается ровно на его границе: за концом прогретого
    отрезка не лежит ничего, и первое же место оттуда придётся ЖДАТЬ - ровно столько,
    сколько стоит поднять ffmpeg и получить от источника первый кусок.

    Разбор ленты сеанса (756 отданных кусков): двадцать мест подряд ушли зрителю из
    прогретого, запас показа (:func:`torrcast.usecases.feed_pack.feed_front._front`) все эти
    секунды стоял мёртво на конце прогретого, а на первом месте за границей показ встал:
    два ``buffering``, три ``freeze`` и 13.08 с потерянной плёнки. Пока источник отвечал,
    незаметно было ничего; источник замолчал на 45 с - и обеспечение кончилось на границе.

    Поэтому упаковка поднимается ЗАРАНЕЕ - за :attr:`_State.seam_lead` секунд плёнки до
    конца прогретого, - и к границе за ней уже стоит живой задел. Цена нулевая там, где
    прогретого впереди много: задел длиннее выдержки считается по тем же файлам, что и
    выдача, и до прогона дело не доходит вовсе.
    """
    if state.vault is None or state.fatal:
        return
    end = slot
    while (
        state.grid.end(end) - state.grid.start(slot) <= state.seam_lead
        and end + 1 < state.grid.count
        and _have(state, end + 1)
    ):
        end += 1
    if state.grid.end(end) - state.grid.start(slot) > state.seam_lead:
        return  # задела впереди больше, чем молчание, которое он обязан пережить
    seam = end + 1
    if seam >= state.grid.count:
        return  # прогретое доходит до конца фильма: за ним паковать нечего
    # Мерка обеспечения та же, что у запроса сегмента: прогон покрывает место, если начат
    # не позже него и отстал не больше чем на :attr:`ahead` кусков. Только что поднятый
    # прогон стоит ровно перед своим первым сегментом, и стык это как отставание не читает -
    # иначе он поднимал бы вторую упаковку в то же место каждые две секунды.
    packer = state.packer
    if (
        packer is not None
        and not packer.halted
        and packer.poll() is None
        and packer.first <= seam <= packer.edge + state.ahead
    ):
        return  # этот прогон уже идёт к стыку - второго тут не надо
    if _state.clock_port.monotonic() - state.restarted < (5.0 if state.offline else 2.0):
        return  # соседний запрос уже поднял упаковку - не толкаемся
    if not state.lock.acquire(blocking=False):
        return  # решение уже принимают; свой кусок ждёт файла, а не очереди
    handed = False
    try:
        state.restarted = _state.clock_port.monotonic()
        journal().mark(
            "упаковка к стыку прогретого",
            слот=seam,
            задел=round(state.grid.end(end) - state.grid.start(slot), 1),
        )
        # Замок отсюда уносит подъём и отпускает его сам: внутри лежит пробный прогон, до
        # минуты по потолку, а тут стоит поток раздачи с готовым прогретым куском в руках.
        _state.spawn(lambda: _raise(state, restart, seam))
        handed = True
    finally:
        if not handed:
            state.lock.release()


def _raise(state: _State, restart: Callable[[int], None], slot: int) -> None:
    """Поднять упаковку с места ``slot``, не занимая собой ответ приёмнику.

    ⚠️ Показ может кончиться, пока прогон поднимают: конец гасит ТОТ прогон, который
    застал (:func:`torrcast.usecases.feed_pack.feed_stop._stop`), а поднятый следом остался
    бы читать раздачу в каталог, которого уже нет.
    """
    try:
        if not state.fatal:
            restart(slot)
        if state.fatal and state.packer is not None:
            state.packer.stop()
    finally:
        state.lock.release()
