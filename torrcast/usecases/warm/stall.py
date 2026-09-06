"""Прогрев встал и след о том, сколько он успел.

Зовут нитка прогрева (:func:`_work`) и сверка укладки (:func:`_verify`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.warm._state as _state
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.warm.line import _line
from torrcast.usecases.warm.settings import BARREN_SPENT, BARREN_TRIES

if TYPE_CHECKING:
    from torrcast.usecases.warm.warmer_state import _State


def _stall(state: _State, why: str) -> None:
    """Прогрев дальше не идёт: сказать это вслух, в журнал и в недельный след."""
    state.trouble = why
    state._say(_line(state))
    _state._environment.mark("прогрев встал", причина=why, секунд=round(state.warmed))
    _trace(state, "stall", why)


def _barren(state: _State, first: int, spent: float) -> None:
    """Заход не дал ни куска: подождать и повторить, а после :data:`BARREN_TRIES` - сдаться.

    Повторять вечно нельзя, а именно это тут и было. Замер на стенде 06-09-2026, «Теория
    большого взрыва» s1e2, последний слот 116 из 117: 30 заходов подряд по 3.5 с, ни
    одного куска, и ни одного слова человеку - ``cast status`` всё это время повторял
    «прогрето 0:20:38 из 0:21:09», как будто работа идёт, а 67 одинаковых строк «жду и
    пробую снова» ушли в журнал службы. То же место роняет и ЖИВОЙ показ (``nonzero dts``
    в его журнале), то есть дело не в прогреве и не в починимой мелочи.

    Признанное недающимся место перестаёт быть целью (:func:`_missing`) - иначе прогрев
    топчется на нём вечно, а точечный перекод тяжёлых мест идёт ПОСЛЕ укладки и не
    начинается вовсе, и тяжёлые куски остаются копией.

    ``spent`` разводит два пустых захода, неразличимых по журналу: пропавшая сеть держит
    ffmpeg до его срока и вернётся сама, недающееся место отваливается мгновенно
    (:data:`BARREN_SPENT`). Считаются только быстрые, и долгий заход череду РВЁТ, а не
    просто не добавляет к ней: иначе два обрыва связи по минуте и один быстрый пустой
    заход дают «три подряд» и хоронят место, которое взялось бы само, - а «подряд» в
    приговоре обязано означать три захода ОДНОЙ природы.
    """
    if spent > BARREN_SPENT:
        state.barren.pop(first, None)
    else:
        state.barren[first] = tries = state.barren.get(first, 0) + 1
        if tries >= BARREN_TRIES:
            state.hopeless.add(first)
            _stall(
                state,
                phrase(
                    "warm.barren_spot",
                    slot=first,
                    minute=f"{state.grid.start(first) / 60:.0f}",
                    tries=tries,
                ),
            )
            return
    state._say(f"прогрев не дал ни куска за {spent:.0f} с - жду и пробую снова")
    _state._environment.sleep(10.0)


def _trace(state: _State, event: str, why: str = "") -> None:
    """Доля прогретого в недельный след - полями, а не строкой журнала.

    Строка (:func:`_line`) остаётся человеку в живом показе, а сюда идут те же числа
    врозь: секунды на диске, длина фильма и вес каталога. По ним и через неделю видно,
    сколько успел прогрев, - без разбора текста.
    """
    _state._environment.emit(
        "warmth",
        event,
        secs=state.warmed,
        dur=state.grid.duration,
        size=state.vault.size(),
        why=why,
    )
