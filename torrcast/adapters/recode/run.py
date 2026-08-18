"""Один заход кодировщика: ffmpeg на куски от ``first`` до ``last`` и замер темпа.

Зовёт его нитка кодировщика (:func:`_work`), и только она."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Final

from torrcast.adapters.recode.hold_head import _head_pending
from torrcast.adapters.recode.preset_for import preset_for
from torrcast.adapters.recode.presets import PRESETS
from torrcast.adapters.recode.yield_to_shrink import _yield_to_shrink
from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.packer import Packer
from torrcast.ports.journal import journal

if TYPE_CHECKING:
    from torrcast.adapters.recode.recoder_state import _State


#: Приоритет процессу кодировщика. Упаковщик (копия + AAC) и TorrServer должны получать
#: процессор раньше него: их работа привязана к реальному времени, а кодировщик работает
#: впрок и опоздание на секунду ему ничего не стоит.
NICE: Final = 15

#: Приоритет захода за ГОЛОВОЙ прогона (:meth:`Recoder.opening`). Голова - исключение из
#: правила выше: её ждёт не запас впрок, а сам старт показа, и каждая её секунда - это
#: секунда чёрного экрана. Замер («Моана 2» 13.3 ГБ, v0 длиной 19.96 с,
#: ultrafast): под ``nice 15`` - 8.05 с, под ``nice 0`` - 5.84 с.
HEAD_NICE: Final = 0


def _run(state: _State, first: int, last: int) -> None:
    """Заход кодировщика: пресет по сроку, цель по длине куска, ffmpeg и замер темпа."""
    seconds = sum(state.grid.span(s) for s in range(first, last + 1))
    # Срок - у ПОСЛЕДНЕГО куска захода: до него кодировщик доберётся позже всех, и
    # именно он решает, каким пресетом идти всему заходу.
    table = state.pace.table()
    preset = preset_for(seconds, state.slack(last), table)
    quickest = table[-1][1]
    # Выкладка стоит на куске этого захода (:meth:`_hold_bulky`) - качество тут больше
    # не торгуется: пока мы выбираем пресет получше, приёмник ждёт наш кусок и никакого
    # другого. Срок у такого захода нулевой по определению.
    if first <= state.blocked <= last:
        preset = PRESETS[-1][0]
    # 🔴 Цель считается от ДЛИНЫ куска, а не берётся константой (TC-483). Заход идёт
    # одним ``-b:v`` на все свои куски, поэтому судит самый длинный из них: на нём
    # прибитые 9 Мбит/с давали 23 МБ при потолке 16, и не влезал сам перекод. Ловить
    # это на выходе (:meth:`torrcast.adapters.stream_pack.packer.Packer.publish`) поздно - процессор
    # уже потрачен на кусок, который заведомо не влезал, и потрачен на критическом пути.
    longest = max(state.grid.span(s) for s in range(first, last + 1))
    encode = state.fit(longest, preset)
    journal().mark(
        "заход",
        первый=first,
        последний=last,
        пресет=preset,
        мбит=round(encode.mbit, 2),
        срок=round(state.slack(last), 1),
        срочный=round(state.slack(first), 1),
    )
    # ⚠️ Пробного прогона тут нет и быть не должно: перекодирующий ffmpeg встаёт по
    # ``-ss`` точно, докатки не делает, и ``at`` равен границе сетки ровно.
    command = ffmpeg_pack_command(
        state.source,
        state.audio,
        str(state.spare / "run"),
        state.grid,
        first,
        state.grid.start(first),
        readrate=0.0,
        burst=0.0,
        encode=encode,
        until=last,
    )
    command = ["nice", "-n", str(HEAD_NICE if first == state.head else NICE), *command]
    began = time.monotonic()
    state.stalled = 0.0
    # Срок, до которого упаковщику имеет смысл придерживать копии этого захода:
    # вдвое больше ожидаемого да ещё десять секунд сверху. Просрочен - копия уходит
    # как есть, потому что подгруз хуже тяжёлого куска.
    speed = state.pace.speed(preset)
    with state.lock:
        # ``last`` тут не украшение: без него огрызок за ``-to`` (секунда фильма
        # вместо десяти) лёг бы в каталог перекода как готовый кусок и уехал бы на ТВ
        # вместо честной копии (:attr:`torrcast.adapters.stream_pack.packer.Packer.last`).
        state.packer = packer = Packer.start(
            command,
            state.spare,
            state.spare / "run",
            first,
            last=last,
            grid=state.grid,
            cap=state.cap,
        )
        state.job = (first, last, began + seconds / speed * 2.0 + 10.0, began, speed)
    try:
        while not state.stopped:
            packer.publish()
            if packer.edge >= last or packer.poll() is not None:
                break
            # Выкладка ужимает тяжёлый кусок на месте - заход замирает и отдаёт ей
            # процессор (:meth:`_yield_to_shrink`). Простой не идёт в замер темпа:
            # он мерит вежливость, а не скорость, и попади он в :class:`Pace` -
            # следующий заход планировался бы по скорости, которой не бывает.
            stall = _yield_to_shrink(state, packer)
            if stall > 0.0:
                state.stalled += stall
                began += stall
                with state.lock:
                    if state.job is not None:
                        state.job = (first, last, state.job[2] + stall, began, speed)
                continue
            # Перемотали за пределы этого захода - он больше не самый нужный.
            gone = state.played > state.grid.end(last)
            far = state.played < state.grid.start(first) - state.ahead
            if gone or far:
                packer.stop(keep_files=True, reason="перемотка")
                return
            # Голова нового прогона важнее любого запаса впрок: её ждёт чёрный экран,
            # а всё остальное - только tmpfs. Доработать заход и потом взяться за
            # голову значит проесть её ожидание чужой работой: замер -
            # заход за `v0` (7 с) съедал ровно столько же от ожидания `v358`.
            if _head_pending(state) and not first <= state.head <= last:
                packer.stop(keep_files=True, reason="голова прогона важнее")
                return
            # Выкладка встала на слишком тяжёлой копии (:meth:`_hold_bulky`) - этот
            # кусок нужен ПРЯМО сейчас, а не впрок. Бросаем заход и берём его отдельно:
            # новый заход начнётся ровно с него, а срок у него нулевой, то есть пресет
            # выйдет самый быстрый (:func:`preset_for`). Заход, который уже идёт над
            # ним самым быстрым пресетом, не трогаем - быстрее всё равно не будет.
            stuck = state.blocked
            if stuck >= 0 and (stuck < first or (stuck <= last and speed < quickest)):
                packer.stop(keep_files=True, reason=f"упаковка встала на v{stuck}")
                return
            time.sleep(0.3)
    finally:
        with state.lock:
            state.packer = None
            state.job = None
        packer.stop(keep_files=True, reason="заход окончен")
    # ⚠️ Считаем по краю СВОЕГО упаковщика, а не по тому, что осталось в каталоге:
    # готовый кусок оттуда уже мог забрать показ (:meth:`Packer.publish`), и глоб
    # каталога честный заход объявлял бы провалившимся. Ровно так «перекодировал v0»
    # печаталось как «не дало ни куска за 7 с» - и стоило часа отладки не там.
    got = list(range(first, min(last, packer.edge) + 1))
    state.done.update(got)
    state.made += len(got)
    state.seconds += sum(state.grid.span(s) for s in got)
    spent = time.monotonic() - began
    if got:
        # Замер сроку, а не отчёту: столько фильма за столько стены вышло ЗДЕСЬ - с
        # подъёмом ffmpeg, чтением из раздачи и соседями (:class:`Pace`).
        made = sum(state.grid.span(s) for s in got)
        ratio = state.pace.record(preset, made, spent)
        journal().mark(
            "темп перекода",
            пресет=preset,
            секунд=round(made, 1),
            стена=round(spent, 1),
            факт=round(made / spent, 2),
            масштаб=round(ratio, 2),
            план=round(state.pace.plan, 2),
            пауза=round(state.stalled, 1),
        )
        state._say(
            f"перекодировал v{first}...v{first + len(got) - 1} "
            f"({seconds:.0f} с фильма за {spent:.0f} с, {preset}, "
            f"{made / spent:.2f}x - план {state.pace.plan:.2f} от таблицы)"
        )
    else:
        state._say(f"перекодирование v{first}...v{last} не дало ни куска за {spent:.0f} с")
        # Чтобы не крутиться на одном и том же месте вечно.
        state.done.update(range(first, last + 1))
