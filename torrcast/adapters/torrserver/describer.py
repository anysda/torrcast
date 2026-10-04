"""Запускает подачу описания в своём потоке и помнит раздачи, снятые процессом.

``add`` по-прежнему уходит магнетом и возвращается сразу: клик не ждёт добычи.
Поток заводится, только если описание есть на диске или есть ссылка на него.

🔴 Подача и снятие одной раздачи разведены (TC-1251). ``rem`` в первые десятки миллисекунд
после ``upload`` роняет TorrServer MatriX.143: служба ещё будит ждущих ``GotInfo``, а кэш
уже закрыт, ``WaitInfo`` берёт nil и падает в горутине, которую никто не перехватывает.
Поэтому подача проверяет снятие под тем же замком, под которым встаёт в работу, а снятие
ждёт конца идущей подачи и выдерживает :data:`SETTLE` после неё.

Подачу из другого процесса того же экземпляра снятие видит по метке на диске
(:class:`~torrcast.adapters.torrserver.upload_mark.UploadMark`) и выдерживает так же.

Ждёт не зовущий, а свой поток снятия: ``drop`` зовёт и отбор показа (``keep_only`` до старта
показа), и снос под замком стенда, а клик до кадра этих секунд не должен. Поток не
служебный (не ``daemon``): выход процесса дожидается ``rem``, иначе раздача пережила бы его.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Final

from torrcast.adapters.prowlarr.torrent_links import LINKS
from torrcast.adapters.system_clock import CLOCK
from torrcast.adapters.torrserver.describe import describe
from torrcast.adapters.torrserver.torrent_http import CALL_TIMEOUT, TorrentHttp
from torrcast.adapters.torrserver.torrent_store import STORE
from torrcast.adapters.torrserver.upload_mark import UploadMark

if TYPE_CHECKING:
    from collections.abc import Callable

    from torrcast.ports.clock import Clock

#: Сколько снятие выжидает после поданного описания. На стенде ``rem`` через 0-20 мс ронял
#: службу или давал перехваченную панику, через 50 мс и дольше - ноль из 90 заходов.
SETTLE: Final = 0.3


class Describer:
    """Один поток на раздачу; раздачу, снятую ``drop``/``park``, не трогает."""

    def __init__(self, clock: Clock = CLOCK) -> None:
        self._lock = threading.Condition()
        self._clock = clock
        self._marks = UploadMark(STORE.folder, clock)
        self._closed: set[str] = set()
        self._running: set[str] = set()
        self._delivering: set[str] = set()
        self._uploaded: dict[str, float] = {}
        self._settling: set[str] = set()

    def close(self, torrent_hash: str, remove: Callable[[], bool]) -> bool:
        """Снять раздачу: описание ей больше не подаётся до нового ``add``.

        Без подачи рядом ``remove`` зовётся сразу и его ответ возвращается. Подача (своя или
        другого процесса) идёт или прошло меньше :data:`SETTLE` - ``remove`` уходит в поток
        снятия, ответ ``True``.
        """
        key = torrent_hash.casefold()
        with self._lock:
            self._closed.add(key)
            if key in self._settling:
                return True  # снятие той же раздачи уже ждёт в своём потоке
            at = self._uploaded.get(key)
            busy = (
                key in self._delivering
                or (at is not None and at + SETTLE > self._clock.monotonic())
                or self._marks.left(key, SETTLE) is not None
            )
            if busy:
                self._settling.add(key)
            else:
                self._uploaded.pop(key, None)
        if not busy:
            return remove()
        threading.Thread(target=self._settle, args=(key, remove), name=f"settle-{key}").start()
        return True

    def _settle(self, key: str, remove: Callable[[], bool]) -> None:
        """Дождаться конца подачи и :data:`SETTLE` после неё, потом снять."""
        try:
            with self._lock:
                self._lock.wait_for(lambda: key not in self._delivering, CALL_TIMEOUT)
                at = self._uploaded.pop(key, None)
            mine = 0.0 if at is None else at + SETTLE - self._clock.monotonic()
            left = max(mine, self._marks.left(key, SETTLE, CALL_TIMEOUT) or 0.0)
            if left > 0:
                self._clock.sleep(left)
        finally:
            with self._lock:
                self._settling.discard(key)
                again = key not in self._closed  # пока ждали, раздачу добавили заново
        if not again:
            remove()

    def dropped(self, torrent_hash: str) -> bool:
        with self._lock:
            return torrent_hash.casefold() in self._closed

    def later(self, base_url: str, torrent_hash: str) -> threading.Thread | None:
        """Запустить подачу описания; нет источника или поток уже идёт - ``None``."""
        key = torrent_hash.casefold()
        with self._lock:
            self._closed.discard(key)
            if key in self._running or not (STORE.has(key) or LINKS.link_for(key)):
                return None
            self._running.add(key)
        thread = threading.Thread(target=self._run, args=(TorrentHttp(base_url), key), daemon=True)
        thread.start()
        return thread

    def _upload(self, http: TorrentHttp, key: str, data: bytes) -> bool:
        """Подать, если раздачу ещё не сняли; снятие ждёт конца подачи под тем же замком."""
        with self._lock:
            if key in self._closed:
                return False
            self._delivering.add(key)
        ok = False
        try:
            with self._marks.delivering(key) as stamp:
                ok = http.upload(key, data)
                if ok:
                    stamp()
        finally:
            with self._lock:
                self._delivering.discard(key)
                if ok:
                    self._uploaded[key] = self._clock.monotonic()
                self._lock.notify_all()
        return ok

    def _run(self, http: TorrentHttp, key: str) -> None:
        try:
            describe(
                key,
                fetch=http.fetch,
                stat=http.stat,
                upload=lambda k, data: self._upload(http, k, data),
                dropped=self.dropped,
            )
        finally:
            with self._lock:
                self._running.discard(key)


#: Описатель процесса: его будит ``TorrServer.add``, ему же говорят о снятии раздачи.
DESCRIBER: Final = Describer()

__all__ = ["DESCRIBER", "SETTLE", "Describer"]
