"""Кладёт позицию, присланную вкладкой; зовёт её ``POST /api/web/position`` (:mod:`web.position`).

Время записи ложится тут же, стенными часами: с этой минуты ходит две секунды между
опросами разных процессов (сама вкладка и держатель показа
:func:`torrcast.usecases.revive_playback._hold._hold`), и молчание вкладки читает
только тот, кто сравнивает СВОЁ сейчас с этой меткой
(:meth:`torrcast.adapters.browser.browser_receiver.BrowserReceiver.position`).
"""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.browser._write_json import _write_json
from torrcast.adapters.browser.web_position_path import web_position_path


def write_web_position(
    out: Path, key: str, pos: float, dur: float, phase: str, wall: float
) -> None:
    """Записать позицию сеанса ``key``: место ``pos``, длину ``dur``, состояние ``phase``."""
    _write_json(
        web_position_path(out),
        {"key": key, "pos": pos, "dur": dur, "phase": phase, "wall": wall},
    )
