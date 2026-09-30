"""Старт следующей серии - на диск заранее, пока текущая только началась.

Зовёт нитка прогрева (:func:`_work`) один раз за серию; шаг ждёт кадра текущего показа.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import torrcast.usecases.warm._state as _state
from torrcast.usecases.warm.chain import _adopt, _nap
from torrcast.usecases.warm.head_spot import _head_spot
from torrcast.usecases.warm.settings import (
    FRAME_STEP,
    HEAD_NICE,
    HEAD_RATE,
    HEAD_TRIES,
    START_GRACE,
)

if TYPE_CHECKING:
    from torrcast.usecases.warm.warmer_state import _State


def _lay_head(state: _State) -> bool:
    """Положить стартовый кусок (:func:`_head_spot`) одним прогоном; ``False`` - нечего.

    Перекод идёт под :data:`HEAD_NICE`, а не под ``nice`` прогрева: на стыке серий
    больше ждать нечего, и под ``nice 19`` этот кусок перекодировался 14.6 с рядом
    с живым показом, а до конца серии оставалось 10 с. Читает он под :data:`HEAD_RATE`:
    один кусок раздачу не отнимет, а шаг и так ждёт запаса показа (:func:`_yield`).
    """
    head = _head_spot(state)
    if head is None:
        return False
    # Копия поверх нужна перекоду ради звука (:func:`_run`), поэтому сперва она. При
    # сплошном перекоде копии нет: первый же заход и есть кусок, который возьмёт показ.
    whole = state.encode is not None
    spot = not whole and state.vault.have(head)
    final = whole or spot
    landing = state.landing = threading.Event() if final else None
    nice, rate = state.nice, state.rate
    state.nice = min(nice, HEAD_NICE) if final else nice
    state.rate = max(rate, HEAD_RATE)
    try:
        state._run(head, head, spot=spot)
    finally:
        state.nice, state.rate = nice, rate
        if landing is not None:
            landing.set()  # после метки: :meth:`hand_over` ждёт её
    return True


def _early_head(state: _State) -> None:
    """Собрать прогрев следующей серии сразу и положить её стартовый кусок.

    Цепочка поднимает следующую серию, только когда эта уже на диске
    (:func:`_chain`), а живым показом - за считанные секунды до стыка: перекод её
    тяжёлого старта в это окно не влезал, и первый кадр ждал его живым. Остальная
    следующая серия ждёт, как и раньше: раздача нужна текущей.

    Шаг не начинается, пока текущий показ не дал кадр на нынешнем месте
    (:func:`_framed`): копия и перекод следующей серии - это раздача и процессор, а
    первый кадр текущей, в том числе после перемотки, важнее. Запас, отданный живой
    упаковкой у конца файла (:meth:`packed`), кадром не считается. Запаса не мерили
    или кадра так и нет - шага нет вовсе, следующую серию поднимет :func:`_chain`.

    Спрашиваем один раз: при сбое сети повторы - дело :func:`_chain`, а прогрев
    текущей серии не имеет права стоять из-за следующей.
    """
    if state.ahead or state.follow is None or state.after is not None:
        return
    if not _framed(state):
        return
    try:
        _yield(state, state)
        following = state.follow()
        if following is None:
            state.follow = None  # фильм или последняя серия: спрашивать нечего никогда
            return
        _adopt(state, following)
        for _ in range(HEAD_TRIES):
            _yield(state, following)
            if state.stopped or not _lay_head(following):
                return
    except Exception:  # прогрев не имеет права ронять показ
        return


def _yield(state: _State, whose: _State) -> None:
    """Переждать живое окно показа (:meth:`_must_yield`), просыпаясь на стоп."""
    while not state.stopped and whose._must_yield():
        _nap(state, 0.5)


def _framed(state: _State) -> bool:
    """Дождаться кадра текущего показа на нынешнем месте (:func:`_shown`), до :data:`START_GRACE`.

    Нулевой запас - приёмник его не меряет вовсе: кадра от него не узнать, и ждать нечего.
    """
    if state.slack <= 0:
        return False
    deadline = _state._environment.monotonic() + START_GRACE
    while not state.stopped and not state.framed and _state._environment.monotonic() < deadline:
        _nap(state, 0.5)
    return state.framed and not state.stopped


def _shown(state: _State, pos: float, playing: bool) -> None:
    """Кадр на нынешнем месте есть, когда указатель сдвинулся между двумя ИГРАЮЩИМИ опросами.

    Ровно так кадр узнаёт и «старт NN с» (:func:`torrcast.usecases.revive_playback._screen.
    _first_frame`): слово ``PLAYING`` приходит раньше картинки, а на входе в него указатель
    ещё докатывается до места захода. Живой прогон: сдвиг 1306.0 -> 1306.3 с на первом
    ``PLAYING`` засчитался кадром, и шаг ушёл на секунду раньше «играю».
    Прыжок дальше :data:`FRAME_STEP` или назад - перемотка: кадра на новом месте ещё не было.
    """
    moved = pos - state.shown_at
    if state.shown_at >= 0 and (moved < 0 or moved > FRAME_STEP):
        state.framed = False
    elif state.shown_playing and playing and moved > 0:
        state.framed = True
    state.shown_at, state.shown_playing = pos, playing
