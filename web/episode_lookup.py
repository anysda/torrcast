"""Список серий выбранной раздачи без старта показа: фоновый разбор с кэшем в памяти.

Карточка сериала, которого никогда не открывали, не хранит ``Entry.episodes`` - его не
бывает без хотя бы одного показа (ТЗ §4.4). Разбор той же раздачи, которую играл бы
показ, спрашивает TorrServer, а его рой может отвечать секундами: ждать это внутри
``GET /api/card`` значило бы повторить зависшее меню, от которого ушла полка (TC-1110).
Разбор идёт фоном; карточка отдаёт то, что готово, и просит вёрстку переспросить
(``X-Torrcast-Partial``, тем же протоколом, что и недоехавшая справка).
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from torrcast.domain._series import _Series
from torrcast.domain.release import Release
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.torrent_engines import TorrentEngines

#: Кто разносит фоновую сборку по потоку; в бою - настоящий поток-демон.
Spawn = Callable[[Callable[[], None]], None]
#: Сколько ждать первый контакт с роем в фоне и весь ответ TorrServer целиком. Карточка
#: файл не играет - спешить сверх этого некуда, но и висеть весь запрос показа тоже
#: незачем: оба числа те же, что и у прогрева показа (:mod:`torrcast.usecases.select._prep`).
GRACE = 8.0
TIMEOUT = 20.0
#: Неудачу переспрашивать не раньше, чем через это время - рой может ожить, а TorrServer
#: стенда - подняться заново. Разобранная раздача сюда не попадает: её ответ окончателен
#: (в том числе честное «раздача без нумерации»), и срока у него нет (:meth:`_build`).
RETRY = 60.0


def _daemon(job: Callable[[], None]) -> None:
    """Боевой запуск фона: отдельный поток-демон, который никого не держит при выходе."""
    threading.Thread(target=job, daemon=True, name="episode-lookup").start()


@dataclass
class EpisodeLookup:
    """Кэш «магнит -> таблица серий» на процесс; строит фон, читает - каждый запрос.

    Фон и часы - подставные ради тестов (:mod:`tests.thread_guard` роняет тест, следующий
    за тем, что оставил настоящий поток жить): подделка зовёт ``spawn`` синхронно, ни разу
    не открывая настоящий сокет.
    """

    engines: TorrentEngines
    spawn: Spawn = _daemon
    clock: Callable[[], float] = time.monotonic
    _table: dict[str, tuple[list[list[int]], float]] = field(default_factory=dict)
    _pending: set[str] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def table(self, release: Release, base_url: str) -> list[list[int]] | None:
        """Таблица серий, если уже разобрана; иначе завести разбор фоном и вернуть ``None``.

        ``None`` значит «спроси ещё раз» - карточка в этом случае показывает только
        счётчик сезонов и метит тело недоехавшим, а вёрстка переспрашивает сама.
        """
        magnet = release.magnet
        now = self.clock()
        with self._lock:
            cached = self._table.get(magnet)
            if cached is not None and cached[1] > now:
                return cached[0]
            if magnet in self._pending:
                return None
            self._pending.add(magnet)
        self.spawn(lambda: self._build(release, base_url))
        # Синхронная подделка (тесты) успевает заполнить кэш до этой строки - живой
        # поток ещё бежит, и следующая же строка честно отдаёт ``None``.
        with self._lock:
            cached = self._table.get(magnet)
            return cached[0] if cached is not None else None

    def _build(self, release: Release, base_url: str) -> None:
        """Разобрать файлы РАЗДАЧИ, которую играл бы показ, и убрать её за собой.

        Показ этой раздачи не начат - держать её в TorrServer больше незачем, тот же
        довод, что и у брошенных запасных раздач (:attr:`_Prep.dropped`).
        """
        table: list[list[int]] = []
        parsed = False
        engine = self.engines(base_url, timeout=TIMEOUT)
        torrent_hash = ""
        try:
            torrent_hash = engine.add(release.magnet)
            files = engine.wait_files(torrent_hash, timeout=TIMEOUT, grace=GRACE)
            table = _Series.table(files, release.season)
            parsed = True
        except TorrcastError:
            table = []
        finally:
            if torrent_hash:
                engine.drop(torrent_hash)
            with self._lock:
                self._table[release.magnet] = (table, self._until(parsed))
                self._pending.discard(release.magnet)

    def _until(self, parsed: bool) -> float:
        """Докуда ряд годен: разобранное - навсегда, неудача - до :data:`RETRY`.

        🔴 Раздача без нумерации и лежащий TorrServer давали ОДНУ пустую таблицу с одним
        сроком, и по его выходе карточка снова метилась недоехавшей: замер 10-09-2026 на
        стенде `.104` - налитая карточка `tv:пассажиры-2:2022` раз в минуту опять просила
        страницу переспросить, и та жгла свои пять доборов на уже готовом ответе. Разбор
        ответил - переспрашивать нечего: содержимое раздачи не меняется.
        """
        return math.inf if parsed else self.clock() + RETRY


__all__ = ["EpisodeLookup", "Spawn"]
