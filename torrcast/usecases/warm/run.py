"""Один прогон ffmpeg прогрева: от края до края участка, на диск и в темпе.

Зовёт его нитка прогрева (:func:`_work`), и только она.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import torrcast.usecases.warm._state as _state
from torrcast.usecases.warm.forecast import _forecast
from torrcast.usecases.warm.lay_heavy import _lay_heavy
from torrcast.usecases.warm.segment_start import segment_start
from torrcast.usecases.warm.settings import RUN_DIR
from torrcast.usecases.warm.stall import _stall
from torrcast.usecases.warm.throttle import _resume, _throttle
from torrcast.usecases.warm.verify import _inspect

if TYPE_CHECKING:
    from torrcast.usecases.warm.warmer_state import _State


def _run(
    state: _State,
    first: int,
    last: int,
    spot: bool = False,
    began_of: Callable[[Path], float] = segment_start,
) -> None:
    """Один прогон ffmpeg: от ``first`` до ``last`` включительно, на диск, в темпе.

    ``spot`` - это не участок, а один тяжёлый кусок, который перекладывается поверх
    своей же копии перекодом (:attr:`spots`). Отдельный короткий прогон тут законен:
    ровно так же, отдельным прогоном на кусок, тяжёлое место берёт и живой показ
    (:class:`torrcast.adapters.recode.Recoder`), то есть стык звука на его границе у показа уже
    есть - и прогретое повторяет его один в один, а не добавляет свой.

    🔴 Где прогон встал на самом деле - :func:`torrcast.adapters.stream_pack.pack_start.pack_start`,
    ровно как у живой упаковки (:meth:`torrcast.usecases.feed_pack.feed.Feed.restart`), а не «где его
    задумала сетка». Разница не бухгалтерская: ``-segment_times`` считаются от ``at``, а муксер
    отмеряет их от ПЕРВОГО ПАКЕТА прогона. Отдали задуманное начало - и все резы захода попросились
    раньше на всю докатку. Замер на живом материале: ``-ss 2901.815`` ставит ffmpeg на 2899.730,
    докатка 2.085 с, и прогретый кусок начинался на 2932.638 вместо 2934.432 - PCR на 1.668 с назад,
    DTS видео на 1.710 с (обратный ход -22 мс уже подтверждённо ронял показ, тут в 75 раз больше).
    Куски при этом лежали под правильными именами и весили правдоподобно, а манифест обещал 10.885 с
    против 12.595 с в файле - около 40 дублированных кадров. Там, где в сдвинутом окне опорных
    кадров не было, рез вставал верно и кусок был побайтово равен живому - отсюда и незаметность.

    ⚠️ Пробный прогон нужен ровно копии. У перекодирующего захода (``spot``, сплошной
    :attr:`encode`) ``-ss`` точен, докатки нет, и измеренное начало увело бы весь заход
    на сегмент назад (:func:`torrcast.adapters.stream_pack.ffmpeg_pack_command.ffmpeg_pack_command`).

    Цена честная: копирующих заходов у прогрева два на фильм - хвост от места показа и
    голова (:meth:`_missing`), - а точечные идут перекодом и пробного не просят вовсе.
    0.5-2.9 с на заход против получаса прогрева не считаются.
    """
    encode = state.spot_encode if spot else state.encode
    at = state.grid.start(first)
    if encode is None:
        at = _state.pack_start(state.source, at)
        _state._environment.mark("пробный прогон прогрева", слот=first, встали=round(at, 3))
    command = _state.ffmpeg_pack_command(
        state.source,
        state.audio,
        str(state.vault.dir / RUN_DIR),
        state.grid,
        first,
        at,
        readrate=state.rate,
        burst=0.0,
        encode=encode,
        until=last,
    )
    command = ["nice", "-n", str(state.nice), *command]
    began = _state._environment.monotonic()
    # Копией заход идёт или перекодом - в журнале обязано стоять словом, а не выводиться
    # из соседней метки «пробный прогон прогрева». Разбор живого показа на этой
    # недоговорённости уже срывался: гипотезу «перекод не успевает, потому что делит
    # процессор с прогревом» проверяли там, где прогрев шёл копией, а копия соседу стоит
    # 2-3 % вместо 33 % (:data:`torrcast.adapters.recode.NEIGHBOUR_TOLL`).
    way, by = ("перекод", "перекодом") if encode is not None else ("копия", "копией")
    _state._environment.mark(
        "прогрев пошёл", первый=first, последний=last, темп=state.rate, точечно=spot, режим=way
    )
    state._say(
        f"тяжёлый v{first} на диске кладу перекодом - тем же, каким его отдаёт показ"
        if spot
        else f"грею на диск с {state.grid.start(first) / 60:.0f}-й минуты {by}, "
        f"темп ×{state.rate:g}"
    )
    with state.lock:
        state.packer = packer = _state.Packer.start(
            command,
            state.vault.dir,
            state.vault.dir / RUN_DIR,
            first,
            last=last,
            grid=state.grid,
            shrink=partial(_lay_heavy, state),
        )
    state.misgrid = -1
    laid = first - 1
    checked = first - 1
    try:
        while not state.stopped:
            packer.publish()
            laid = _inspect(state, laid, min(packer.edge, last), began_of)
            if state.misgrid >= 0 or packer.edge >= last or packer.poll() is not None:
                break
            if not spot and laid > checked:
                # Заход - это весь остаток фильма, и за него и бюджет, и запас
                # раздела меняются: перепроверяем по ходу укладки, а не раз на
                # входе. По мере укладки, а не по таймеру: ``fit`` взвешивает весь
                # каталог, и лишний раз гонять его каждые полсекунды незачем.
                checked = laid
                tight = state.vault.fit(int(_forecast(state, laid + 1, last)))
                if tight:
                    _stall(state, tight)
                    break
            _throttle(state, packer)
            _state._environment.sleep(0.5)
        if state.misgrid < 0:
            # Мёртвый ffmpeg дописал последний кусок, но выложить его успевает уже
            # не цикл (:meth:`torrcast.adapters.stream_pack.packer.Packer.publish`) - и сверить тоже.
            packer.publish()
            _inspect(state, laid, min(packer.edge, last), began_of)
    finally:
        _resume(state, packer)
        with state.lock:
            state.packer = None
        packer.stop(keep_files=True, reason="прогрев окончен")
        state.vault.touch()
    if state.misgrid >= 0:
        # Заход, вставший не туда, кладёт мимо сетки весь свой участок: доводить его
        # до конца значит намолотить ещё сотню таких же кусков.
        return
    got = max(0, min(last, packer.edge) - first + 1)
    spent = _state._environment.monotonic() - began
    if spot and got:
        # Метка ставится ПОСЛЕ выкладки: оборвался прогон - на месте куска осталась
        # копия, и следующий круг возьмётся за него снова.
        with contextlib.suppress(OSError):
            state.vault.spot(first).touch()
    if got and packer.poll() not in (0, None) and packer.edge < last:
        # Прогон оборвался сам - почти всегда это пропавшая сеть. Не авария:
        # следующий круг начнёт с первого непрогретого куска, когда сеть вернётся.
        state.breaks += 1
        state._say(f"прогрев оборвался на {state.grid.end(packer.edge) / 60:.0f}-й минуте")
        _state._environment.sleep(5.0)
    elif not got:
        state._say(f"прогрев не дал ни куска за {spent:.0f} с - жду и пробую снова")
        _state._environment.sleep(10.0)
