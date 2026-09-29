"""Голова показа на полку прогрева заранее: перекод места целиком или картинка со звуком копии.

Зовёт её :class:`torrcast.usecases.playback.head_ahead.HeadAhead`, и только она.
"""

from __future__ import annotations

import contextlib
import os
import threading
from typing import TYPE_CHECKING

import torrcast.usecases.warm._state as _state
from torrcast.ports.journal.slot import journal
from torrcast.usecases.warm.head_work import head_work

if TYPE_CHECKING:
    from pathlib import Path

    from torrcast.domain.segment_container import SegmentContainer
    from torrcast.ports.recode.encoding_rate import EncodingRate
    from torrcast.ports.warm_environment.warm_pack import WarmPack
    from torrcast.usecases.warm._state import Grid
    from torrcast.usecases.warm.vault import Vault

#: Шаг, которым заход смотрит на оба ffmpeg.
_STEP: float = 0.1
#: Потолок выкладки обоих заходов. Копия - только донор звука, и тяжёлая голова и есть
#: повод захода; вес склейки судит :func:`spot_out` потолком приёмника.
_UNCAPPED: int = 1 << 40


def lay_head(
    vault: Vault,
    source: str,
    audio: int,
    voice: str,
    grid: Grid,
    slot: int,
    encode: EncodingRate,
    cap: int,
    container: SegmentContainer,
    halt: threading.Event,
    *,
    splice: bool = True,
) -> bool:
    """Положить тяжёлое место ``slot`` на полку склейкой, как его отдал бы показ.

    Голый перекод со своим AAC на полку класть нельзя: стык с копией соседа гасит конвейер
    приёмника (:func:`torrcast.adapters.stream_pack.spot_out.spot_out`). Поэтому рядом с
    перекодом идёт копия того же места, и звук берётся у неё, как у точечного прогона
    прогрева (:func:`torrcast.usecases.warm.run._run`). Оба ffmpeg идут разом и во всю
    скорость: этот кусок ждёт первый кадр.

    Файл, который перекодом идёт целиком (``splice`` ложь), склейки не знает: его показ
    пакует одним ffmpeg со своим звуком, и голова - это ровно его кусок, без копии рядом.

    Правда - кусок лежит на полке (свой или уже был), ложь - заход снят или не вышел.
    """
    if vault.have(slot) and (not splice or vault.spot(slot).exists()):
        return True
    vault.open()
    work = head_work(vault.dir, slot)  # пока он есть, показ ждёт голову, а не пакует её
    _state._environment.remove_tree(work)
    at = grid.start(slot)
    runs = [_pack(work / "code", source, audio, voice, grid, slot, at, at, encode, container)]
    if splice:
        seek, landed = _state.settle_start(source, at)
        runs.append(
            _pack(work / "copy", source, audio, voice, grid, slot, landed, seek, None, container)
        )
    journal().mark("голова на полку пошла", слот=slot, склейка=splice)
    try:
        while not halt.is_set():
            over = [_over(run, slot) for run in runs]  # смотреть каждый, без короткого замыкания
            if all(over):
                break
            _state._environment.sleep(_STEP)
        for run in runs:
            run.publish()
    finally:
        for run in runs:
            run.stop(keep_files=True, reason="голова на полке")
    laid = work / "code" / vault.path(slot).name
    donor = work / "copy" / vault.path(slot).name
    done = not halt.is_set() and laid.exists()
    if splice:
        done = done and donor.exists() and _state.spot_out(slot, laid, donor, cap, container)
    else:
        done = done and laid.stat().st_size <= cap
    if done:
        with contextlib.suppress(OSError):
            os.replace(laid, vault.path(slot))
            if splice:
                vault.served.mark(slot)
            vault.touch()
    _state._environment.remove_tree(work)
    journal().mark("голова на полке" if done else "голова на полку не легла", слот=slot)
    return bool(done) and vault.have(slot)


def _over(run: WarmPack, slot: int) -> bool:
    """Заход дал кусок ``slot`` или ffmpeg вышел."""
    run.publish()
    return run.edge >= slot or run.poll() is not None


def _pack(
    out: Path,
    source: str,
    audio: int,
    voice: str,
    grid: Grid,
    slot: int,
    at: float,
    seek: float,
    encode: EncodingRate | None,
    container: SegmentContainer,
) -> WarmPack:
    """Один ffmpeg на одно место: копия (``encode`` пуст) или перекод."""
    out.mkdir(parents=True, exist_ok=True)
    command = _state.ffmpeg_pack_command(
        source,
        audio,
        str(out / "run"),
        grid,
        slot,
        at,
        readrate=0.0,
        burst=0.0,
        encode=encode,
        until=slot,
        seek=seek,
        voice=voice,
        container=container,
    )
    return _state.Packer.start(
        command, out, out / "run", slot, last=slot, grid=grid,
        cap=_UNCAPPED, container=container, outward=True,
    )  # fmt: skip
