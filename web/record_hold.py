"""Записанные раздачи подключены, пока открыта страница с ними: ``POST /api/hold``.

Продолжение платит за проверку записи первым контактом роя
(:func:`torrcast.usecases.select._dead_release._dead_release`): раздачу, которую TorrServer
закрыл по ``TorrentDisconnectTimeout`` или снёс конец показа, служба заново сводит с пирами
4-36 с. Главная называет ключи плиток «Продолжить», карточка - свой ключ, раз в
:data:`BEAT`; держатель поднимает их записанные раздачи и не даёт службе их закрыть, пока
страница зовёт. Байты первых записей ряда читает до клика :class:`web.record_warm.RecordWarm`,
отпущенная раздача закрывается с кэшем на диске службы
(:meth:`torrcast.ports.parking_engine.ParkingEngine.park`).

Заводятся они по одной: двадцать раздач истории, поднятые разом, тянули метаданные живой
раздачи 15-19 с вместо 0.2-3 с (мимо torrcast), и «Играть» с закладки ждала
22.8 с. Следующая заводится, когда прошлая ответила метаданными; первой идёт ключ, который
страница назвала первым. Мёртвую раздачу держатель отпускает и не трогает :data:`MUTE`.
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
from torrcast.ports.parking_engine import ParkingEngine
from torrcast.ports.state_store.slot import store
from torrcast.ports.torrent_engine import TorrentEngine
from torrcast.usecases.select_bench._bench_keep import _keep_step, _Timed
from torrcast.usecases.torrent_claims import CLAIMS
from torrcast.usecases.torrents import _held_by_show
from web.record_warm import RecordWarm
from web.warm_job import WarmJob

#: Как часто страница называет свои записи; то же число стоит в ``web/static/warm.js``.
BEAT: Final = 10.0
#: Сколько живёт аренда без нового зова: три пропущенных зова, и раздача отпускается.
LEASE: Final = 3 * BEAT
#: Больше записей разом не держится: каждая - рой и соединения службы.
HOLD_MAX: Final = 20
#: Терпение одного запроса к службе: зов страницы не должен копить висящие потоки.
TIMEOUT: Final = 10.0
#: Столько TorrServer ждёт метаданные новой раздачи, потом закрывает её сам
#: («timeout connection get torrent info»): дольше её не ждут и следующую не держат.
COLD: Final = 20.0
#: Шаг, которым заводимая раздача спрашивает метаданные, а очередь - свой черёд.
COLD_STEP: Final = 0.5
#: Сколько мёртвая раздача не заводится снова: без пиров она лишь занимала бы очередь.
MUTE: Final = 300.0


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
    warmer: RecordWarm = field(default_factory=RecordWarm)
    _keys: dict[str, str] = field(default_factory=dict, repr=False)
    _lease: dict[str, float] = field(default_factory=dict, repr=False)
    _held: set[str] = field(default_factory=set, repr=False)
    _queue: list[str] = field(default_factory=list, repr=False)
    _mute: dict[str, float] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def touch(self, base_url: str, keys: list[str]) -> int:
        """Продлить аренду записей этих ключей; сколько раздач начали держать заново."""
        entries = self.entries()
        found = [(key, entries.get(key)) for key in keys[:HOLD_MAX]]
        keyed = {entry.magnet: key for key, entry in reversed(found) if entry and entry.magnet}
        magnets = list(dict.fromkeys(entry.magnet for _, entry in found if entry and entry.magnet))
        fresh: list[str] = []
        with self._lock:
            now = self.clock()
            magnets = [magnet for magnet in magnets if self._mute.get(magnet, 0.0) <= now]
            self._keys.update(keyed)
            for magnet in magnets:
                self._lease[magnet] = now + LEASE
                if magnet not in self._held:
                    self._held.add(magnet)
                    fresh.append(magnet)
            named = [magnet for magnet in magnets if magnet in self._queue]
            self._queue = named + [m for m in self._queue if m not in named] + fresh
        self.warmer.name(magnets)
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
        dead = False
        try:
            step = _keep_step(engine.disconnect_timeout()) if isinstance(engine, _Timed) else BEAT
            while self._leased(magnet) and not self._turn(magnet):
                self.wait(COLD_STEP)
            torrent_hash, dead = self._wake(engine, magnet)
            while not dead:
                self._offer(engine, magnet, torrent_hash)
                self.wait(step)
                if not self._leased(magnet):
                    break
                torrent_hash = self._renew(engine, magnet) or torrent_hash
        finally:
            self.warmer.forget(magnet)
            with self._lock:
                if magnet in self._queue:
                    self._queue.remove(magnet)
                if dead:
                    self._mute[magnet] = self.clock() + MUTE
            free = bool(torrent_hash) and CLAIMS.unclaim(torrent_hash, self)
            if free and not _held_by_show(torrent_hash):
                with contextlib.suppress(TorrcastError):
                    # Закрыть, а не снести: снос стирает кэш службы, и «Продолжить» тянул
                    # кусок закладки из роя заново, до 30 с.
                    close = engine.park if isinstance(engine, ParkingEngine) else engine.drop
                    close(torrent_hash)
            with self._lock:
                self._held.discard(magnet)

    def _turn(self, magnet: str) -> bool:
        with self._lock:
            return not self._queue or self._queue[0] == magnet

    def _wake(self, engine: TorrentEngine, magnet: str) -> tuple[str, bool]:
        """Завести раздачу и дождаться её метаданных; «мертва» - служба ответила, пиров нет."""
        began = self.clock()
        torrent_hash = ""
        while self._leased(magnet):
            with contextlib.suppress(TorrcastError):
                torrent_hash = torrent_hash or CLAIMS.adding(magnet, self, engine.add)
                if engine.files(torrent_hash):
                    break
            if self.clock() - began >= COLD:
                return torrent_hash, bool(torrent_hash)
            self.wait(COLD_STEP)
        with self._lock:
            if magnet in self._queue:
                self._queue.remove(magnet)
        return torrent_hash, False

    def _offer(self, engine: TorrentEngine, magnet: str, torrent_hash: str) -> None:
        """Предложить прогреву файл записи с её закладки; закладка сдвинулась - снова."""
        if not torrent_hash or not self.warmer.wants(magnet):
            return
        entry = self.entries().get(self._keys.get(magnet, ""))
        if entry is None or entry.magnet != magnet:
            return
        with contextlib.suppress(TorrcastError):
            files = engine.files(torrent_hash)
            name = next((f.name for f in files if f.index == entry.file_idx), "")
            source = engine.stream_url(torrent_hash, entry.file_idx)
            self.warmer.offer(WarmJob(magnet, source, entry.pos, name))

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
