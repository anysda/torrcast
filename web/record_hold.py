"""Записанные раздачи подключены, пока открыта страница с ними: ``POST /api/hold``.

Продолжение платит за проверку записи первым контактом роя
(:func:`torrcast.usecases.select._dead_release._dead_release`): раздачу, которую TorrServer
закрыл по ``TorrentDisconnectTimeout`` или снёс конец показа, служба заново сводит с пирами
4-36 с. Главная называет ключи плиток «Продолжить», карточка - свой ключ, раз в
:data:`BEAT`; держатель поднимает их записанные раздачи и не даёт службе их закрыть, пока
страница зовёт. Читателя у раздачи нет, поэтому байты картины сами не тянутся.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.domain.entry import Entry
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.state_store.slot import store
from torrcast.ports.torrent_engine import TorrentEngine
from torrcast.usecases.select_bench._bench_keep import _keep_step, _Timed
from torrcast.usecases.torrent_claims import CLAIMS
from torrcast.usecases.torrents import _held_by_show

#: Как часто страница называет свои записи; то же число стоит в ``web/static/warm.js``.
BEAT: Final = 10.0
#: Сколько живёт аренда без нового зова: три пропущенных зова, и раздача отпускается.
LEASE: Final = 3 * BEAT
#: Больше записей разом не держится: каждая - рой и соединения службы.
HOLD_MAX: Final = 20
#: Терпение одного запроса к службе: зов страницы не должен копить висящие потоки.
TIMEOUT: Final = 10.0


def _thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="torrcast-record-hold", daemon=True).start()


def _entries() -> dict[str, Entry]:
    return store().load().entries


@dataclass
class RecordHold:
    """Аренды записанных раздач по магниту; часы, ожидание и поток подставные ради тестов."""

    engines: Callable[..., TorrentEngine] = TorrServer
    entries: Callable[[], dict[str, Entry]] = _entries
    clock: Callable[[], float] = time.monotonic
    wait: Callable[[float], object] = time.sleep
    spawn: Callable[[Callable[[], None]], None] = _thread
    _lease: dict[str, float] = field(default_factory=dict, repr=False)
    _held: set[str] = field(default_factory=set, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def touch(self, base_url: str, keys: list[str]) -> int:
        """Продлить аренду записей этих ключей; сколько раздач начали держать заново."""
        entries = self.entries()
        found = (entries.get(key) for key in keys[:HOLD_MAX])
        magnets = list(dict.fromkeys(entry.magnet for entry in found if entry and entry.magnet))
        fresh: list[str] = []
        with self._lock:
            until = self.clock() + LEASE
            for magnet in magnets:
                self._lease[magnet] = until
                if magnet not in self._held:
                    self._held.add(magnet)
                    fresh.append(magnet)
        for magnet in fresh:
            self.spawn(lambda magnet=magnet: self._hold(base_url, magnet))  # type: ignore[misc]
        return len(fresh)

    def held(self) -> set[str]:
        """Магниты, которые держатся прямо сейчас."""
        with self._lock:
            return set(self._held)

    def _leased(self, magnet: str) -> bool:
        with self._lock:
            return self._lease.get(magnet, 0.0) > self.clock()

    def _hold(self, base_url: str, magnet: str) -> None:
        """Держать раздачу, пока жива аренда, и отпустить её, если она больше ничья.

        🔴 Из списка держимых магнит уходит ПОСЛЕ сноса: иначе новый зов заведёт второй
        держатель той же раздачи, и снос первого выдернет её из-под второго (TC-1285).
        """
        engine = self.engines(base_url, timeout=TIMEOUT)
        torrent_hash = ""
        try:
            step = _keep_step(engine.disconnect_timeout()) if isinstance(engine, _Timed) else BEAT
            while self._leased(magnet):
                torrent_hash = self._renew(engine, magnet) or torrent_hash
                self.wait(step)
        finally:
            free = bool(torrent_hash) and CLAIMS.unclaim(torrent_hash, self)
            if free and not _held_by_show(torrent_hash):
                with contextlib.suppress(TorrcastError):
                    engine.drop(torrent_hash)
            with self._lock:
                self._held.discard(magnet)

    def _renew(self, engine: TorrentEngine, magnet: str) -> str:
        """Поднять раздачу и продлить её срок; служба промолчала - спросит следующий шаг.

        ``add`` идемпотентен и один будит раздачу, лежащую в базе службы: её туда кладёт
        и закрытие по сроку, и снос в конце показа. ``get`` продлевает срок живой
        (:mod:`torrcast.usecases.select_bench._bench_keep`).
        """
        with contextlib.suppress(TorrcastError):
            torrent_hash = CLAIMS.adding(magnet, self, engine.add)
            engine.files(torrent_hash)
            return torrent_hash
        return ""


#: Держатель процесса: главная и карточки всех вкладок зовут один и тот же.
RECORD_HOLD: Final = RecordHold()
