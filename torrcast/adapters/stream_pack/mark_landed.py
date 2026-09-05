"""Кладёт настоящее место, откуда показ реально пошёл; зовёт сценарий показа после захода.

Закладка не годится для сверки указателя после TC-1002: показ вправе законно сесть НИЖЕ
неё (:func:`torrcast.usecases.feed_pack.feed_restart._begin` берёт ближайший опорный кадр
не позже закладки, а отвод назад на неудачном заходе отступает ещё дальше). Настоящее
место посадки знает только сам показ, а его CLI спрашивает не по памяти - другого
процесса, - а по этому файлу.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from torrcast.adapters.stream_pack.landed_path import landed_path


def mark_landed(out: Path, at: float) -> None:
    """Записать настоящее место старта. Неудача не роняет показ - только его доказательство."""
    with contextlib.suppress(OSError):
        landed_path(out).write_text(repr(at), encoding="utf-8")
