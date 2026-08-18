"""Ротация ленты: старьё сносится по сроку, а излишек - по весу каталога.

Зовёт её укладка пакета на диск (:func:`_flush`) раз в сутки на каталог."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, Final

from torrcast.adapters.filesystem.trace_journal.log_path import _PREFIX, _SUFFIX

if TYPE_CHECKING:
    from pathlib import Path

#: Держим след неделю и не даём ему съесть диск.
RETAIN_DAYS: Final = 7
MAX_BYTES: Final = 64 * 1024 * 1024


def _prune(marked: str, directory: Path, ceiling: int = MAX_BYTES) -> str:
    """Ротация: старше семи суток - снести, свыше потолка места - снести самые старые.

    Раз в сутки на каталог: чаще незачем, а на каждый пакет - лишние ``stat``. ``marked`` -
    метка «уже прибрано», она же и возвращается: метка несёт и каталог, поэтому смена пути
    ленты (``TORRCAST_LOG``) прокручивает ротацию по новому месту сразу.

    Потолок места назван параметром: боевое число - умолчание
    (:data:`MAX_BYTES`), а порядок сноса меряется потолком поменьше, чтобы не разводить
    в тесте шестьдесят четыре мегабайта настоящей ленты.
    """
    today = f"{directory}:{time.strftime('%Y%m%d')}"
    if marked == today:
        return marked
    with contextlib.suppress(OSError):
        files = sorted(directory.glob(f"{_PREFIX}*{_SUFFIX}"))
        cutoff = time.strftime("%Y%m%d", time.localtime(time.time() - RETAIN_DAYS * 86400))
        kept: list[Path] = []
        for path in files:
            day = path.name[len(_PREFIX) : -len(_SUFFIX)]
            if day < cutoff:
                path.unlink(missing_ok=True)
            else:
                kept.append(path)
        total = 0
        for path in reversed(kept):  # даты сортируются хронологически, новые - в хвосте
            with contextlib.suppress(OSError):
                total += path.stat().st_size
                if total > ceiling:
                    path.unlink(missing_ok=True)
    return today
