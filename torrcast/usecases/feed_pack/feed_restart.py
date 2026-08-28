"""Начало упаковки с нужного места: перемотка, возврат с паузы или старт показа.

Зовёт отсюда решение об упаковке (:meth:`torrcast.usecases.feed_pack.feed.Feed.restart`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.feed_pack._state as _state
from torrcast.domain.hls_settings import PACK_DIR, SPLIT_SLACK
from torrcast.ports.journal.slot import journal
from torrcast.ports.pack_run.pack_factory import PackShrink

if TYPE_CHECKING:
    from torrcast.usecases.feed_pack.feed_state import _State


def _restart(state: _State, slot: int, shrink: PackShrink) -> None:
    """Начать упаковку с сегмента ``slot``: перемотка, возврат с паузы или старт показа.

    Границы сегментов от места старта не зависят (:class:`Grid`), поэтому уже
    упакованное не выбрасывается: под именем ``vN`` и до, и после перезапуска лежит
    ровно одно и то же место фильма. Убирать приходится только то, что прошлый прогон
    не успел дописать, — а этого наружу и не попадало.
    """
    if state.packer is not None:
        state.packer.stop(keep_files=True)
    # ⚠️ Кодировщик узнаёт о новом месте показа ПЕРВЫМ делом, до пробного прогона
    # (0.5-1.7 с): голову прогона он обязан начать не позже упаковщика, иначе
    # придерживать её копию будет нечего и первый сегмент уйдёт тяжёлым.
    if state.recoder is not None:
        state.recoder.opening(slot)
    # ⚠️ Перекодирующему прогону пробный не нужен и вреден: по ``-ss`` он встаёт точно,
    # докатки не делает (:func:`ffmpeg_pack_command`), и измеренное ``at`` увело бы
    # весь прогон на сегмент назад. Заодно это минус 0.5-1.7 с из пути старта - ровно
    # та цена, которой сплошной перекод отчасти и оплачивает свою голову.
    at = seek = state.grid.start(slot)
    if state.encode is None:
        # Место захода считается по карте опорных кадров, а пробный прогон остаётся
        # запасным путём и сверкой: он идёт один раз на файл (:func:`pack_start`).
        # Дороже всего это на перемотке - там прогон был на пути к картинке каждый раз.
        #
        # 🔴 Заход, вставший ПОЗЖЕ границы, не производит плёнку между границей и собой
        # вовсе, и приёмник упирается в дыру. Поэтому спрашивается не «где встанем», а
        # «с какого места зайти, чтобы не проскочить границу»
        # (:func:`torrcast.adapters.stream_pack.settle_start.settle_start`).
        seek, at = _state.settle_start(state.source, state.grid.start(slot))
        journal().mark("заход упаковки", слот=slot, встали=round(at, 3))
    command = _state.ffmpeg_pack_command(
        state.source,
        state.audio,
        str(state.out / PACK_DIR),
        state.grid,
        slot,
        at,
        state.readrate,
        state.burst,
        encode=state.encode,
        seek=seek,
        voice=state.voice,
        container=state.container,
        video_tag="hvc1" if state.video_codec.startswith("hvc1") else "",
    )
    state.restarted = _state.clock_port.monotonic()
    state.packer = _state.Packer.start(
        command,
        state.out,
        state.out / PACK_DIR,
        slot,
        spare=None if state.recoder is None else state.recoder.spare,
        told=None if state.recoder is None else state.recoder.note,
        hold=None if state.recoder is None else state.recoder.holding,
        shrink=shrink,
        at=at,
        rate=state.readrate,
        burst=state.burst,
        grid=state.grid,
        cap=state.cap,
        container=state.container,
    )
    drop = state.grid.start(slot) - at
    state._say(
        f"упаковка с {state.grid.start(slot):.1f} с"
        + (f" (докатка {drop:.1f} с)" if drop > SPLIT_SLACK else "")
    )
