"""Черновик карты опорных кадров: своё имя каждому писателю. Общая часть полки карт."""

from __future__ import annotations

import os
import threading
from pathlib import Path


def _keys_draft(cache: Path) -> Path:
    """Черновик кэша карты - свой у каждого писателя.

    Замок на карту берётся не всегда (протух, каталог только для чтения), а на одно имя
    два писателя пишут вперемешку - и ``replace`` выложил бы наружу склейку двух половин.
    """
    return cache.with_suffix(f".{os.getpid()}-{threading.get_ident()}.tmp")
