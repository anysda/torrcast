"""Картинки найденных картин для списка обзора: имя сразу, байты - следом.

Список находок обязан приходить не медленнее, чем раньше: круг поиска и так идёт холодным
около пяти секунд, а сходить за десятком постеров внутри того же ответа значило бы сложить
одно время с другим. Поэтому ответ уносит только ИМЯ картинки на маршруте ``/api/poster/``,
а байты ищутся фоном и догоняют его: пока Home Assistant рисует список и спрашивает
картинки, постер обычно уже лежит. Найденное ложится на полку
(:class:`hass.poster_shelf.PosterShelf`) и второй раз берётся с неё, без сети вовсе.

🔴 Имя картинки - отпечаток НАЗВАНИЯ, ГОДА и РОДА вместе, и год у картины сверен
(:func:`hass.poster_find.poster_of_the_year`): «Матрица» 1999 года и «Матрица» 2021-го -
разные картины, и постер соседки хуже, чем никакого.

Постера нет - строка остаётся строкой: ни заглушки, ни рамки, ни слов «нет обложки».
Промах откладывает следующий поход за той же картиной (:data:`_RETRY`), иначе список из
десяти находок стучал бы по Википедии на каждый заход в обзор.
"""

from __future__ import annotations

import hashlib
import queue
import threading
import time
from collections.abc import Callable
from typing import Final

from hass.picture_type import picture_type
from hass.poster_find import Correct, Poster
from hass.poster_lookup import _wiki_correction
from hass.poster_of_the_year import poster_of_the_year
from hass.poster_shelf import PosterShelf
from torrcast.adapters.wiki.wiki_poster import WikiPoster
from torrcast.domain.json_value import JsonValue
from torrcast.runtime.facts_wiring import FACTS

#: Поле записи выдачи, в котором едет имя картинки. Его читает
#: :func:`custom_components.torrcast.browse.search_media`; нет поля - нет и картинки.
FIELD: Final = "poster"
#: Хвост имени картины на общей полке: картинка играющего (:class:`hass.posters.Posters`)
#: лежит там под теми же названием, годом и родом, но год у неё НЕ сверен - и без хвоста
#: постер соседней картины приезжал бы в список прямо с полки, минуя сверку.
_CHECKED: Final = "year-checked"
#: Сколько ждём Википедию на один запрос, секунды.
_TIMEOUT: Final = 8.0
#: Через сколько секунд после промаха спрашиваем о той же картине снова.
_RETRY: Final = 300.0
#: Сколько картинок ищется разом: находок бывает десяток, и уходить за всеми сразу - это
#: уже стук по Википедии, а не поиск. Поток берётся под работу и уходит, когда очередь
#: опустела: постоянная бригада пережила бы пробу, которая её подняла.
_WORKERS: Final = 4
#: Сколько ждёт запрос картинки, которая ещё в пути, секунды. Ждёт ОДИН запрос в своём
#: потоке сервера; ни снимок, ни показ этого ожидания не видят.
_WAIT: Final = 6.0
#: Сколько найденных картинок держим наготове: список находок бывает длинным.
_KEEP: Final = 64

_Job = tuple[str, str, str, int | None, str]


class HitPosters:
    """Постеры списка находок: имя выдаётся сразу, картинка ищется фоном."""

    def __init__(
        self,
        poster: Poster | None = None,
        correct: Correct | None = None,
        shelf: PosterShelf | None = None,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._poster = poster
        self._correct = correct
        self._shelf = PosterShelf() if shelf is None else shelf
        self._now = now
        self._lock = threading.Lock()
        self._queue: queue.Queue[_Job] = queue.Queue()
        self._made: dict[str, bytes] = {}
        self._pending: dict[str, threading.Event] = {}
        self._tried: dict[str, float] = {}
        self._busy = 0

    def offer(self, results: list[JsonValue]) -> list[JsonValue]:
        """Те же записи выдачи, каждая с именем своей картинки, если та будет."""
        return [self._offered(record) for record in results]

    def read(self, name: str) -> tuple[bytes, str] | None:
        """Байты картинки и её тип; она ещё в пути - подождать, но не бесконечно.

        Список этим не задержан: он ушёл человеку раньше, и ждёт картинку браузер.
        """
        with self._lock:
            body = self._made.get(name)
            waiting = None if body else self._pending.get(name)
        if body is None and waiting is not None:
            waiting.wait(_WAIT)
            with self._lock:
                body = self._made.get(name)
        return (body, picture_type(body)) if body else None

    def _offered(self, record: JsonValue) -> JsonValue:
        if not isinstance(record, dict):
            return record
        about = _about(record)
        if about is None:
            return record
        name = self._started(about)
        return record if name is None else {**record, FIELD: name}

    def _started(self, about: tuple[str, int | None, str]) -> str | None:
        """Имя картинки этой картины; её нет и не искали - поставить в очередь за ней."""
        identity = "|".join((about[0], str(about[1]), about[2], _CHECKED))
        name = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        with self._lock:
            if name in self._made or name in self._pending:
                return name
            if self._now() < self._tried.get(name, 0.0):
                return None
        kept = self._shelf.read(identity)
        with self._lock:
            if kept:
                self._keep(name, kept)
                return name
            if name in self._pending:
                return name
            self._pending[name] = threading.Event()
        self._hire((name, identity, *about))
        return name

    def _hire(self, job: _Job) -> None:
        """Поставить картинку в очередь и, если есть кого поднять, поднять за ней поток.

        Очередь пополняется и поток поднимается под одним замком: иначе картинка встаёт в
        очередь ровно в тот миг, когда последний поток из неё уходит, и ждёт зря.
        """
        with self._lock:
            self._queue.put(job)
            hiring = self._busy < _WORKERS
            if hiring:
                self._busy += 1
        if hiring:
            threading.Thread(target=self._work, daemon=True, name="hit-poster").start()

    def _work(self) -> None:
        """Брать из очереди, пока она не опустела, и уходить - бригады тут не держат."""
        while True:
            try:
                job = self._queue.get_nowait()
            except queue.Empty:
                with self._lock:
                    if self._queue.empty():
                        self._busy -= 1
                        return
                continue
            self._made_of(job)

    def _made_of(self, job: _Job) -> None:
        name, identity, title, year, kind = job
        body = self._look(title, year, kind)
        if body:
            self._shelf.write(identity, body)
        with self._lock:
            waiting = self._pending.pop(name, None)
            if body:
                self._keep(name, body)
            else:
                self._tried[name] = self._now() + _RETRY
        if waiting is not None:
            waiting.set()

    def _look(self, title: str, year: int | None, kind: str) -> bytes | None:
        poster = self._poster or WikiPoster(FACTS.client, FACTS.client).poster
        correct = self._correct or (None if self._poster else _wiki_correction)
        return poster_of_the_year(title, year, kind, _TIMEOUT, poster, correct)

    def _keep(self, name: str, body: bytes) -> None:
        """Положить картинку готовой, вытеснив самую давнюю, если их стало много."""
        self._made[name] = body
        while len(self._made) > _KEEP:
            self._made.pop(next(iter(self._made)))


def _about(record: JsonValue) -> tuple[str, int | None, str] | None:
    """Название, год и род картины из записи выдачи; без названия картинку не ищут.

    Род сводится к тем же двум словам, какими его знает картинка карточки
    (:func:`hass.posters._kind`): полка у них общая, и третье слово завело бы на ней
    вторую запись про ту же картину.
    """
    if not isinstance(record, dict):
        return None
    title, year, kind = record.get("title"), record.get("year"), record.get("kind")
    if not isinstance(title, str) or not title.strip():
        return None
    named = year if isinstance(year, int) and not isinstance(year, bool) else None
    return title.strip(), named, "tv" if kind == "tv" else "movie"


#: Мост держит один список находок на всех: имя, выданное поиском, спрашивают потом
#: отдельным запросом за картинкой (:meth:`hass.posters.Posters.read`).
hits = HitPosters()
