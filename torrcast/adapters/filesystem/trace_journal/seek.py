"""Поля записи ``play/seek``: перемотка и время до КАРТИНКИ после неё.

Зовёт её сторож перемотки у приёмника, читает разбор ``cast log``."""

from __future__ import annotations

from torrcast.adapters.filesystem.trace_journal.emit import emit


def seek(frm: float, to: float, wait: float | None, why: str = "") -> None:
    """Перемотка: откуда, куда и сколько секунд ждали КАРТИНКУ после неё.

    Ожидание меряется до сдвига указателя с места приземления, а не до слова ``PLAYING``:
    приёмник говорит его раньше первого кадра (:attr:`torrcast.cast.ChromecastReceiver.
    PICTURE_STEP`). ``wait=None`` - картинки после этой перемотки не случилось вовсе, и
    ``why`` называет, чем всё кончилось.
    """
    extra = {"why": why} if why else {}
    emit(
        "play",
        "seek",
        frm=round(frm, 1),
        to=round(to, 1),
        wait=None if wait is None else round(wait, 2),
        **extra,
    )
