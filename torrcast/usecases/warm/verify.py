"""Сверка уложенного с сеткой: кусок обязан начаться там, где обещал манифест.

Зовёт её заход прогрева (:func:`_run`) на каждом выложенном куске.
"""

from __future__ import annotations

import contextlib
import math
from typing import TYPE_CHECKING

import torrcast.usecases.warm._state as _state
from torrcast.usecases.warm.segment_start import segment_start
from torrcast.usecases.warm.settings import SKEW_MAX, SKEW_TRIES
from torrcast.usecases.warm.stall import _stall

if TYPE_CHECKING:
    from torrcast.usecases.warm.warmer_state import _State


def _inspect(state: _State, done: int, edge: int) -> int:
    """Сверить с сеткой всё, что легло после ``done`` и не дальше ``edge``.

    Возвращает новую границу сверенного. Обход не обрывается на первом же промахе, и
    это важнее, чем кажется: ``publish`` выкладывает пачкой (:meth:`_run` опрашивает
    его раз в полсекунды), а заход, вставший не туда, разъезжается с сеткой ЦЕЛИКОМ.
    Оборви обход - и остальные куски пачки остались бы лежать в показе непроверенными,
    то есть сторож ловил бы ровно один кусок из четырёх.
    """
    for slot in range(max(done + 1, 0), edge + 1):
        _verify(state, slot)
    return max(done, edge)


def _verify(state: _State, slot: int) -> bool:
    """Кусок лёг на своё место сетки? Ложь - он уже убран и в показ не пойдёт.

    🔴 Ради этой сверки карточка и написана. Дефект, из-за которого прогрев резал куски
    мимо сетки, прожил незамеченным не потому, что был хитрым, а потому, что уложенное
    никто не сверял: код верил намерению (``-segment_times`` от нужного места), а
    муксер отмерял резы от ПЕРВОГО ПАКЕТА прогона (:meth:`_run`). Куски при этом лежали
    под правильными именами и весили правдоподобно, а начинались на 1.4-3.8 с раньше
    своих границ - на стыке с живой упаковкой метки шли НАЗАД до 1.7 с, около сорока
    кадров дублировалось. Здоровым он выглядел выборочно: там, где в сдвинутом окне не
    оказывалось опорного кадра, рез случайно вставал верно и кусок побайтово совпадал с
    живым. Поэтому сверяется КАЖДЫЙ уложенный кусок, а не один на заход.

    Ловится только сдвиг НАЗАД, и это не полумера. Раньше своей границы кусок начаться
    не может ни по одной законной причине: обе упаковки заходят от измеренного начала
    (:func:`torrcast.adapters.stream_pack.pack_start.pack_start`), а муксер режет по первому опорному
    кадру не раньше границы. Позже - может, и законно: на сетке, чьи границы не попали на опорные
    кадры, муксер ждёт следующего кадра, и ровно так же ведёт себя живая упаковка - её кусок в этом
    месте побайтово тот же самый. Выбрасывать такое значило бы выбрасывать то, что показ и так
    отдаёт с диска; расхождение сетки с потоком - это про карту опорных кадров, и меряет его
    :meth:`torrcast.adapters.stream_pack.packer.Packer.drift`.

    ``nan`` (не прочли) - пропускаем. Сторож, который бракует по незнанию, дороже того
    дефекта, ради которого он поставлен.

    Забракованный кусок именно СТИРАЕТСЯ, а не помечается: показ ищет прогретое глобом
    каталога (:meth:`Vault.slots`, :meth:`torrcast.usecases.feed_pack.feed.Feed.segment`), и никакой
    пометки он не читает. Отдачу это не роняет даже в самый неудачный момент - файл,
    пропавший между проверкой и чтением, отдача уже переживает (``OSError`` →
    404 → приёмник просит снова, :meth:`torrcast.adapters.http_server._handler._Handler._read`).
    """
    began = segment_start(state.vault.path(slot))
    # Метка куска - это время фильма ПЛЮС начало ленты, одно на все заходы
    # (:attr:`torrcast.adapters.stream_pack.grid.Grid.origin`): сверять надо с тем же числом, иначе
    # порог сдвига у релизов с B-кадрами съеден на треть ещё до всякого промаха.
    want = state.grid.start(slot) + state.grid.origin
    if math.isnan(began) or began > want - SKEW_MAX:
        return True
    tries = state.skews.get(slot, 0) + 1
    state.skews[slot] = tries
    state.misgrid = slot if state.misgrid < 0 else state.misgrid
    # Дыра - это честное «тут не прогрето»: файла нет, значит нет его и в
    # :meth:`Vault.slots`, значит "прогрето целиком" (:attr:`done`) не наступит и
    # следующая серия в работу не возьмётся (:meth:`_chain`). Ровно так же считается
    # неготовым тяжёлый кусок, под которым лежит копия (:meth:`_spots_left`).
    hole = tries >= SKEW_TRIES
    with contextlib.suppress(OSError):
        state.vault.path(slot).unlink(missing_ok=True)
        state.vault.spot(slot).unlink(missing_ok=True)
    _state._environment.emit("skew", slot=slot, want=want, got=began, hole=hole)
    _state._environment.mark(
        "кусок прогрева мимо сетки", слот=slot, сдвиг=round(began - want, 3), дыра=hole
    )
    where = f"v{slot} на {want / 60:.0f}-й минуте лёг мимо сетки ({began - want:+.2f} с)"
    if hole:
        _stall(state, f"{where} - это место осталось непрогретым")
    else:
        state._say(f"{where} - перекладываю его заново")
    return False
