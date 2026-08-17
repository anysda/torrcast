"""Придержать ли копию куска ради перекода, который вот-вот будет готов.

Зовёт его выкладка сегмента наружу (:meth:`Packer.publish`) на каждом куске."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from torrcast.adapters.recode.hold_bulky import _hold_bulky
from torrcast.adapters.recode.hold_head import _hold_head

if TYPE_CHECKING:
    from torrcast.adapters.recode.recoder_state import _State


def _holding(state: _State, slot: int, size: int = 0) -> bool:
    """Придержать ли копию этого куска ради перекода, который вот-вот будет готов.

    Правило одно и оно про срок, а не про расстояние: ждать стоит ровно тогда, когда
    перекод успеет **раньше**, чем показ дойдёт до этого места. Плоский порог «держим
    всё, что дальше N секунд» тут не работает в обе стороны — живой прогон на Q70D
    показал оба края: v359 (26 Мбит/с) при пороге 25 с не придержали, хотя кодировщику
    было нужно три секунды, а v360 придержали и отпустили раньше, чем заход дошёл до
    него, — и оба ушли копией, и оба уронили показ в BUFFERING.

    Кусок, до которого показ уже дошёл, не держим никогда: ожидание под носом у
    показа — это и есть подгруз. **Кроме одного** — головы прогона (:meth:`opening`):
    показ стоит ровно на ней, картинки ещё нет ни одного кадра, и ждать тут значит
    не подгружаться, а стартовать. Уйди голова копией — приёмник встаёт на первой же
    секунде показа в тяжёлом месте (старт, resume, перемотка). Ожидание
    ограничено :attr:`head_wait` и стоит ровно один ultrafast-сегмент (2.3–3.6 с).

    ⚠️ **Одно исключение стоит выше всех сроков: копия тяжелее потолка.**
    Срок тут ни при чём — такой кусок не «хуже», он гарантированно валит приёмник
    (замер: 19.4 МБ — стоп 8 с, 24 МБ — потеря сессии целиком). Поэтому
    решает отдельное правило (:meth:`_hold_bulky`), и оно про факт, а не про срок.
    """
    now = time.monotonic()
    # Перекод уже лежит - держать нечего, :meth:`Packer.publish` возьмёт его сам.
    if state.ready(slot) is not None:
        state._unstick(slot)
        return False
    # Копию тяжелее потолка по сроку не отпускаем вовсе - ни на голове, ни в середине.
    if state.oversize(slot, size):
        return _hold_bulky(state, slot, now)
    if slot == state.head:
        return _hold_head(state, now)
    left = state.grid.start(slot) - state.played
    if left <= 0:
        return False
    job = state.job
    if job is None:
        # Заход не идёт: кодировщик либо ещё поднимается (первый раз), либо стоит
        # МЕЖДУ заходами - и то и другое секунды, а не минуты.
        #
        # ⚠️ Раньше тут стоял отказ по истечении :attr:`grace`, и он стоил живого
        # прогона: заход за головой длился 8 с при форе 6 с, а очередь идёт от места
        # показа вперёд - то есть следующим кодировщик взялся бы ровно за этот кусок.
        # В журнале это выглядело как «тяжёлый v359 (26 Мбит/с) ушёл копией: заход
        # не идёт», а на экране - как 16 опросов BUFFERING из 34.
        if slot not in set(state.targets):
            return False
        warm = max(state.startup, state.grace - (now - state.began))
        quickest = state.pace.table()[-1][1]
        return state.grid.span(slot) / quickest + warm + state.hold_guard <= left
    first, last, until, since, speed = job
    if slot < first or now >= until:
        return False
    if slot <= last:
        todo = sum(state.grid.span(k) for k in range(first, slot + 1)) / speed - (now - since)
        return max(0.0, todo) + state.hold_guard <= left
    # Кусок ЗА текущим заходом. Раньше тут стоял отказ - и он честно стоил живого
    # прогона: заход за головой берёт один кусок (:meth:`_pick`), а упаковщик за эти
    # пять секунд успевал выложить копией три следующих тяжёлых. Считаем так же, как
    # внутри захода: кодировщику остаётся доделать этот заход, а дальше он пойдёт
    # самым быстрым пресетом - до срока ему деваться некуда.
    # Дальше следующего захода (:data:`RUN_MAX`) планов у кодировщика нет, и гадать
    # за него нельзя: там всё решит перемотка, потолок кэша и срок соседей.
    if slot > last + state.run_max or slot not in set(state.targets):
        return False
    rest = sum(state.grid.span(k) for k in range(first, last + 1)) / speed - (now - since)
    quickest = state.pace.table()[-1][1]
    rest += sum(state.grid.span(k) for k in range(last + 1, slot + 1)) / quickest
    return max(0.0, rest) + state.hold_guard <= left
