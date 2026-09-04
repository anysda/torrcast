"""Дочитал ли прогон вход до конца и что он нарезал на самом деле.

Спрашивают отсюда выкладка и горячий путь показа (:mod:`torrcast.usecases.feed_pack`).
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from torrcast.adapters.stream_pack._segment_files import _names
from torrcast.adapters.stream_probe.segment_slot import segment_slot
from torrcast.domain.hls_settings import PACK_LIST, PACK_SHORT_SECONDS

if TYPE_CHECKING:
    from pathlib import Path

    from torrcast.adapters.stream_pack.packer_state import _State
    from torrcast.ports.feed_grid import FeedGrid


def _finished(state: _State) -> bool:
    """Прогон дочитал вход до конца - а не просто вышел из процесса.

    🔴 Ноль от ffmpeg этого не доказывает. Вход, умерший на середине, ffmpeg
    отмечает строкой ``Error during demuxing: Input/output error`` - и **выходит
    нулём**. Замер: 108 обрывов на 108 местах файла, ноль вышел 4 раза, и трижды
    последний кусок оказался дописан не до конца. На одном и том же месте исход не
    повторяется - это гонка между концом чтения и концом записи, поэтому редкость
    тут ничего не значит: по одному коду возврата обрезок (замер: от нуля до 9.4 с
    вместо обещанных 10) уезжает зрителю как готовый кусок, тихо и без единой жалобы
    в журнале. А оборванный файл - вход не рвётся, а кончается - даёт ноль всегда:
    12 прогонов из 12.

    🔴 TC-864, .avi с B-кадрами: тот же вход, тот же прогон, а код скачет - один
    заход отдаёт код 183 и кусок в 0 байт (честный брак), другой на том же месте
    выходит **нулём** с тем же пустым куском. Код тут не судья и в другую сторону:
    ничто не мешает прогону, честно дочитавшему вход и дописавшему последний кусок
    по сетке, упасть на закрытии с ненулевым кодом - и один голый код списал бы
    целый кусок в брак. Поэтому решает не код сам по себе, а пара: что о прогоне
    говорит сетка (:func:`_reached`) и что весит сам произведённый кусок - код
    остаётся доводом ровно там, где сеткой сверить нечего.

    Куски за пределом захода (:attr:`last`) в счёт не идут: заход кодировщика
    ограничен ``-to`` с запасом в секунду, и огрызок за этим пределом короче своего
    места по замыслу, а не по аварии.

    Считается один раз на прогон: у мёртвого процесса ни файлы, ни список уже не
    меняются, а спрашивают отсюда и выкладка, и горячий путь показа.
    """
    if state.whole is None:
        code = state.proc.poll()
        if code is None:
            return False  # процесс ещё жив - сверять пока нечего
        state.whole = _reached(state, code)
    return state.whole


def _reached(state: _State, code: int) -> bool:
    """Обещание сетки, а где сверить нечем - код возврата (:func:`_finished`)."""
    grid = state.grid
    if grid is None:
        return code == 0
    mine = sorted(
        (slot, name)
        for name in _names(state.run)
        for slot in [segment_slot(name)]
        if slot >= 0 and (state.last < 0 or slot <= state.last)
    )
    if not mine:
        # Прогон не написал ни одного своего куска - сеткой сверять нечего, и
        # ответ несёт один лишь код: пустое место бывает и законным (перемотка в
        # самый конец), и битым (TC-864: муксер отказал ПЕРВОМУ же пакету).
        return code == 0
    tail, tail_name = mine[-1]
    ends = {slot: end for slot, _began, end in _cuts(state)}
    if tail not in ends:
        # Кусок закрыт, а строки о нём нет: список ведёт тот же ffmpeg и пишет её
        # ровно на закрытии (``-segment_list_flags +live``). Верить тут нечему.
        return False
    if not _weighed(state.run / tail_name):
        # TC-864: строка списка нарезки лжёт временем закрытия и на пустом куске -
        # муксер отказал каждому пакету, а список всё равно закрылся по границе.
        # Свой вес куска список не пишет, и это спрашивается у самого файла.
        return False
    return ends[tail] >= grid.end(tail) - PACK_SHORT_SECONDS


def _weighed(chunk: Path) -> bool:
    """Кусок и правда что-то весит - список нарезки об этом ничего не знает.

    Замер TC-864: муксер, отказавший первому же пакету (``first pts and dts value
    must be set``), кладёт кусок в **0 байт** - и делает это под обоими кодами
    возврата подряд, 183 и 0. Список нарезки при этом ничем не отличает такой кусок
    от настоящего: строку о закрытии пишет тот же ffmpeg, который только что не
    записал в файл ни байта.
    """
    try:
        return chunk.stat().st_size > 0
    except OSError:
        return False


def _cuts(state: _State) -> list[tuple[int, float, float]]:
    """Что ffmpeg нарезал на самом деле: ``(сегмент, начало, конец)`` по его же списку.

    Нужно ровно для одного: сверить факт с манифестом (:func:`_drift`). Первую строку
    списка приходится пропускать — в ней ffmpeg пишет начало прогона нулём.
    """
    found: list[tuple[int, float, float]] = []
    try:
        text = (state.run / PACK_LIST).read_text("utf-8", "replace")
    except OSError:
        return found
    for line in text.splitlines():
        parts = line.strip().rstrip(",").split(",")
        if len(parts) < 3:
            continue
        slot = segment_slot(parts[0].rsplit("/", 1)[-1])
        with contextlib.suppress(ValueError):
            found.append((slot, float(parts[1]), float(parts[2])))
    return found


def _drift(state: _State, grid: FeedGrid) -> float:
    """Насколько нарезанное разошлось с обещанным в манифесте, секунды.

    Ноль (точнее, доли кадра) — манифест не врёт: ``EXTINF`` совпадает с фактом.
    Больше кадра — повод не верить нарезке и сказать об этом в журнал: значит, карта
    опорных кадров разошлась с потоком.

    Начало ленты (:attr:`torrcast.adapters.stream_pack.grid.Grid.origin`) вычитается: ffmpeg пишет в
    свой список уже сдвинутые метки, и без этого вычитания «расхождение с манифестом» на каждом
    фильме с B-кадрами показывало бы ровно этот сдвиг вместо нуля.
    """
    worst = 0.0
    for slot, began, _ in _cuts(state)[1:]:
        if slot >= state.first:
            worst = max(worst, abs(began - grid.origin - grid.start(slot)))
    return worst
