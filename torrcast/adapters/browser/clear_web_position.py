"""Убирает запись позиции прошлого сеанса; зовёт её приёмник-браузер перед новым показом.

Каталог сегментов один на все показы подряд
(:mod:`torrcast.usecases.playback.hls_root`), а запись прошлой позиции местом НОВОГО
сеанса не является - тем же основанием, что и у
:func:`torrcast.adapters.stream_pack.forget_landed.forget_landed`.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from torrcast.adapters.browser.web_position_path import web_position_path


def clear_web_position(out: Path) -> None:
    """Убрать запись позиции; файла и не было - не беда."""
    with contextlib.suppress(OSError):
        web_position_path(out).unlink(missing_ok=True)
