"""Убирает число настоящей посадки прошлого показа; зовёт подготовка каталога.

Каталог сегментов один на все показы подряд (:mod:`torrcast.adapters.stream_pack.hls_dir`),
а :func:`torrcast.adapters.stream_pack.read_landed.read_landed` берёт запись файла как
правду о ТЕКУЩЕМ показе, чем бы она ни была раньше. Число прошлого показа местом посадки
нового не является - как и его флажок картинки не доказывает нового кадра.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from torrcast.adapters.stream_pack.landed_path import landed_path


def forget_landed(out: Path) -> None:
    """Убрать число посадки: новый показ обязан положить своё, а не унаследовать чужое."""
    with contextlib.suppress(OSError):
        landed_path(out).unlink(missing_ok=True)
