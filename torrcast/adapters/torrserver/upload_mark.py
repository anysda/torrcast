"""Метка подачи описания на диске: чужую подачу видит снятие из другого процесса.

Замок :class:`~torrcast.adapters.torrserver.describer.Describer` живёт в процессе, а одну
раздачу экземпляра трогают два: страница подаёт описание карточке, показ на выходе снимает
свои раздачи. ``rem`` через миллисекунды после чужого ``upload`` роняет TorrServer так же,
как после своего (TC-1251). Поэтому подача держит на метке ``flock`` и по концу ставит ей
стенное время, а снятие, увидев замок или время моложе выдержки, ждёт.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from torrcast.ports.clock import Clock

#: Как часто снятие спрашивает, отпущен ли замок чужой подачи, секунды.
POLL: Final = 0.05


class UploadMark:
    """Файл ``.<хэш>.upload`` в каталоге описаний: замок подачи и время её конца."""

    def __init__(self, folder: Callable[[], Path], clock: Clock) -> None:
        self._folder = folder
        self._clock = clock

    @contextlib.contextmanager
    def delivering(self, key: str) -> Iterator[Callable[[], None]]:
        """Держать метку, пока идёт подача; отданный вызов ставит время её конца."""
        fd = self._open(key, os.O_RDWR | os.O_CREAT)
        try:
            if fd is not None:
                fcntl.flock(fd, fcntl.LOCK_EX)
            yield lambda: self._stamp(fd)
        finally:
            if fd is not None:
                os.close(fd)

    def left(self, key: str, settle: float, timeout: float = 0.0) -> float | None:
        """Сколько ещё выдерживать после подачи любого процесса; ``None`` - нечего.

        Идущая подача держит замок: ``timeout`` - сколько ждать её конца. Не дождались -
        выдерживается полный ``settle``, как будто она кончилась только что.
        """
        fd = self._open(key, os.O_RDONLY)
        if fd is None:
            return None
        try:
            deadline = self._clock.monotonic() + timeout
            while not _shared(fd):
                if self._clock.monotonic() >= deadline:
                    return settle
                self._clock.sleep(POLL)
            left = os.fstat(fd).st_mtime + settle - self._clock.wall()
        finally:
            os.close(fd)
        # Время метки ставят чужие часы: дольше самой выдержки ждать нечего.
        return min(left, settle) if left > 0 else None

    @staticmethod
    def name(key: str) -> str:
        """Имя метки раздачи в каталоге описаний: скрытое, подрезка ``*.torrent`` её не видит."""
        return f".{key}.upload"

    def _stamp(self, fd: int | None) -> None:
        if fd is not None:
            now = self._clock.wall()
            with contextlib.suppress(OSError):
                os.utime(fd, (now, now))

    def _open(self, key: str, flags: int) -> int | None:
        folder = self._folder()
        try:
            if flags & os.O_CREAT:
                folder.mkdir(parents=True, exist_ok=True)
            return os.open(folder / UploadMark.name(key), flags, 0o644)
        except OSError:
            return None


def _shared(fd: int) -> bool:
    """Взять замок на чтение без ожидания; занят подачей - ``False``."""
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


__all__ = ["POLL", "UploadMark"]
