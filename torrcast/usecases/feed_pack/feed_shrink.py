"""Последний шанс тяжёлого куска: ужать его на месте или честно пропустить.

Зовёт отсюда выкладка упаковщика (:attr:`torrcast.adapters.stream_pack.packer.Packer.shrink`).
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import torrcast.usecases.feed_pack._state as _state
from torrcast.domain.hls_settings import SHRINK_DIR
from torrcast.ports.journal.slot import journal

if TYPE_CHECKING:
    from torrcast.ports.pack_run.pack_run import PackRun
    from torrcast.usecases.feed_pack.feed_state import _State


def _shrink(state: _State, slot: int, size: int = 0) -> bool:
    """Ужать кусок, который не влез в потолок приёмника, прямо сейчас; ``False`` - пропуск.

    Зовётся из :meth:`Packer.publish` с последнего гейта: копия тяжелее потолка
    (или перекод, который и сам не влез), а ждать кодировщика уже не стали -
    предохранитель ожидания её отпустил (:meth:`torrcast.adapters.recode.recoder.Recoder.holding`).
    Без этого звонка выкладка вставала на таком куске навсегда: край не двигался,
    сама копия не удалялась, а всё за ней копилось в памяти до потолка несданного;
    потолок гасил прогон, запрос приёмника поднимал его заново - и круг
    повторялся каждые несколько минут, потому что тяжёлый кусок детерминирован.

    Ужатие - один короткий прогон ffmpeg ровно на этот сегмент, самым быстрым
    пресетом и с целью, посчитанной под потолки приёмника
    (:meth:`torrcast.adapters.recode.encode.Encode.fit`).

    🔴 Потолков ДВА, и они разной природы (TC-495). Вес куска - один; битрейт,
    который приёмник тянет (:attr:`torrcast.adapters.recode.recoder.Recoder.threshold`), - второй, и
    первая версия ужатия смотрела только на вес. Живой показ 11-08: ужатие сработало
    на трёх ранних кусках и отдало наружу 9.65, 8.33 и **10.94** Мбит/с при потолке
    около десяти - четыре подгруза в первую минуту, и ранние места ровно эти. Кусок,
    влезающий по весу, роняет показ по битрейту: чем короче кусок, тем больше
    мегабит в секунду в те же 16 МБ помещается.

    Ждать можно: запрос этого места и так держится до :attr:`wait`, а секунда
    фильма самым быстрым пресетом стоит заметно дешевле секунды стены. Потолок
    ожидания тот же, что у предохранителя кодировщика
    (:attr:`torrcast.adapters.recode.recoder.Recoder.over_wait`).
    """
    recoder = state.recoder
    if slot in state.skipped:
        return False  # решение по этому месту принято и сказано ровно один раз
    if recoder is None:
        # Ужимать нечем: перекод выключен настройкой или профиль тяжести не построился.
        return _skip(state, slot, size, "ужимать нечем")
    if state.encode is not None:
        # На сплошном перекоде чужой заход в середину потока - это смена SPS на
        # ходу, а её приёмник не переживает (:data:`RECODE_CODECS`).
        return _skip(state, slot, size, "ужать нельзя")
    with state.shrink_lock:
        if slot in state.skipped:
            return False
        ready = recoder.ready(slot)
        if ready is not None:
            with contextlib.suppress(OSError):
                if 0 < ready.stat().st_size <= state.cap:
                    return True  # пока ждали замок, перекод доехал сам
        span = state.grid.span(slot)
        # Оба потолка приёмника разом: вес куска (:attr:`cap`) и битрейт, который он
        # тянет (порог кодировщика - то же число). Считает их одно место на весь
        # проект, иначе о потолке появился бы третий источник правды.
        encode = recoder.fit(span, recoder.pace.table()[-1][0])
        mbit = encode.mbit
        run = recoder.spare / SHRINK_DIR
        weight = f" ({size / 1e6:.0f} МБ)" if size > 0 else ""
        state._say(f"v{slot} тяжелее потолка{weight} - ужимаю на месте до {mbit:.1f} Мбит/с")
        journal().mark("ужатие на месте", слот=slot, мбит=round(mbit, 2))
        command = _state.ffmpeg_pack_command(
            state.source,
            state.audio,
            str(run),
            state.grid,
            slot,
            state.grid.start(slot),
            0.0,
            0.0,
            encode=encode,
            until=slot,
        )
        packer: PackRun | None = None
        try:
            packer = _state.Packer.start(
                command,
                recoder.spare,
                run,
                slot,
                last=slot,
                grid=state.grid,
                cap=state.cap,
            )
            deadline = _state.clock_port.monotonic() + recoder.over_wait
            while (
                packer.edge < slot
                and packer.poll() is None
                and _state.clock_port.monotonic() < deadline
            ):
                packer.publish()
                _state.clock_port.sleep(0.2)
            packer.publish()
        except Exception:  # не поднялся ffmpeg, не открылся вход - честный пропуск
            packer = None
        finally:
            if packer is not None:
                packer.stop(keep_files=True, reason="ужатие на месте окончено")
    ready = recoder.ready(slot)
    fits = False
    if ready is not None:
        with contextlib.suppress(OSError):
            fits = 0 < ready.stat().st_size <= state.cap
    if fits:
        return True
    return _skip(state, slot, size, "ужать не вышло")


def _skip(state: _State, slot: int, size: int, reason: str) -> bool:
    """Честный пропуск места, которое нельзя отдать приёмнику: один раз и вслух.

    Возвращает ``False`` - выкладка выбросит копию и пойдёт дальше
    (:meth:`Packer.publish`). Само место запоминается (:attr:`skipped`): запрос
    его перепаковки не поднимает - тяжёлый кусок детерминирован, второй прогон
    над ним получит ровно ту же копию, - но и 404 в ответ не получает (TC-501):
    имя уже обещано манифестом, а 404 приёмник переживает хуже тишины.
    """
    state.skipped.add(slot)
    if state.recoder is not None:
        with contextlib.suppress(Exception):
            state.recoder.done.add(slot)  # кодировщику за это место браться уже незачем
    weight = f" ({size / 1e6:.0f} МБ)" if size > 0 else ""
    state._say(
        f"⚠️ v{slot} пропускаю: кусок тяжелее потолка{weight}, а {reason} - "
        "этого места в показе не будет"
    )
    journal().mark("пропуск тяжёлого куска", слот=slot, мб=round(size / 1e6))
    return False
