"""Картинка играющей картины для карточки плеера: постер, а нет его - кадр показа."""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from typing import Final

from hass.picture_type import picture_type
from hass.poster_lookup import _manifest, _poster_names, _wiki_correction
from hass.poster_shelf import PosterShelf
from torrcast.adapters.ffmpeg.frame_shot import frame_shot
from torrcast.adapters.wiki.wiki_poster import WikiPoster
from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.runtime.facts_wiring import FACTS

#: Начало адреса картинки на серве. Наружу за ней Home Assistant не ходит НИКОГДА:
#: постер скачивает себе серв, а карточке отдаёт своим маршрутом в локальной сети.
#: Иначе картинку тянул бы клиент - через ту самую сеть, где режут по SNI.
ROUTE: Final = "/api/poster/"
#: Сколько ждём Википедию на один запрос, секунды.
_TIMEOUT: Final = 8.0
#: Через сколько секунд после промаха пробуем снова. Промах бывает и настоящим (статьи
#: нет), и временным (429, сеть легла), а различить их отсюда нечем. Поэтому не «никогда
#: больше», но и не «на каждый опрос»: карточку опрашивают раз в несколько секунд, и без
#: этой отсрочки промах превратился бы в ровный стук по Википедии на весь показ.
_RETRY: Final = 300.0
#: Сколько картинок держим наготове. Больше одной - чтобы карточка не осталась без
#: байтов ровно в тот миг, когда показ уже сменился, а Home Assistant ещё тянет прошлую.
_KEEP: Final = 4

_Poster = Callable[[str, int | None, str, float], bytes | None]
_Frame = Callable[[str], bytes | None]
_Correct = Callable[[str, int, str, float], str]
_Stream = Callable[[], str]


class Posters:
    """Картинка того, что играет: постер из Википедии, а не нашлось - кадр из показа.

    Работа идёт ФОНОМ, а снимок отвечает тем, что уже готово. Снимок серва спрашивают
    раз в несколько секунд, и ждать в нём похода в Википедию нельзя: карточка плеера
    замерла бы на всё время ожидания, а вместе с ней замерли бы полоса времени и пульт.
    Поэтому первый опрос после начала показа отвечает пустотой, а картинка приезжает
    следующим - секундой позже.

    🔴 Отпечаток картинки - это отпечаток её БАЙТОВ, а не адреса. Без него Home Assistant
    прилепит первую картинку к карточке и не сменит её на следующем показе: `media_image_hash`
    - ровно тот ключ, которым он решает, тянуть ли картинку заново.
    """

    def __init__(
        self,
        poster: _Poster | None = None,
        frame: _Frame = frame_shot,
        shelf: PosterShelf | None = None,
        now: Callable[[], float] = time.monotonic,
        correct: _Correct | None = None,
    ) -> None:
        source = WikiPoster(FACTS.client, FACTS.client)
        self._poster = poster or source.poster
        self._correct = (
            correct if correct is not None else (None if poster is not None else _wiki_correction)
        )
        self._frame = frame
        self._shelf = PosterShelf() if shelf is None else shelf
        self._now = now
        self._lock = threading.Lock()
        self._made: dict[str, tuple[str, bytes]] = {}
        self._working: set[str] = set()
        self._tried: dict[str, float] = {}

    def picture(self, shown: PlaybackSnapshot | None, stream: _Stream) -> tuple[str, str]:
        """Адрес картинки на серве и её отпечаток; готовой ещё нет - две пустых строки.

        Адрес раздачи спрашивается ССЫЛКОЙ, а не значением: он нужен одному лишь
        запасному пути, а карточку опрашивают раз в несколько секунд весь показ, и
        собирать его на каждый опрос ради картинки, которая уже готова, незачем.
        """
        if shown is None or not shown.title:
            return "", ""
        key = _key(shown)
        with self._lock:
            made = self._made.get(key)
            if made is not None:
                return ROUTE + made[0], made[0]
            if key in self._working or self._now() < self._tried.get(key, 0.0):
                return "", ""
            self._working.add(key)
        worker = threading.Thread(
            target=self._resolve, args=(key, shown, stream), daemon=True, name="poster"
        )
        worker.start()
        return "", ""

    def read(self, name: str) -> tuple[bytes, str] | None:
        """Байты картинки и её тип по имени из адреса; чужое имя - ``None``.

        Ищется имя среди готовых, а не собирается путь из него: имя приезжает снаружи, и
        собранный из него путь - это чужой файл на диске серва.
        """
        with self._lock:
            for made, body in self._made.values():
                if made == name:
                    return body, picture_type(body)
        return None

    def _resolve(self, key: str, shown: PlaybackSnapshot, stream: _Stream) -> None:
        """Найти картинку и положить её готовой; не нашлось - отложить следующую попытку.

        Запасной путь берёт кадр по адресу раздачи, и адреса может не быть вовсе: у
        оборванного показа на его месте стоит фраза для человека, а не ссылка
        (:meth:`~torrcast.adapters.unit_playback_session.UnitPlaybackSession.stream_address`).
        Тогда картинки не будет ни постером, ни кадром - и попытка просто откладывается.
        """
        body = self._found(shown)
        where = stream() if body is None else ""
        if body is None and where.startswith("http"):
            body = self._frame(_manifest(where))
        with self._lock:
            self._working.discard(key)
            if not body:
                self._tried[key] = self._now() + _RETRY
                return
            self._made[key] = (hashlib.sha256(body).hexdigest()[:16], body)
            while len(self._made) > _KEEP:
                self._made.pop(next(iter(self._made)))

    def _found(self, shown: PlaybackSnapshot) -> bytes | None:
        """Постер: сперва с полки, потом из Википедии. Сеть не ответила - постера нет.

        Исключение тут не глотается, а ПЕРЕВОДИТСЯ в «постера нет»: выше стоит запасной
        путь, и для него 429, оборванная сеть и картина без английской статьи означают
        одно и то же - карточке нужен кадр. Настоящий отказ виден в другом месте: он
        откладывает следующую попытку (:data:`_RETRY`), а не тонет молча.
        """
        identity = _identity(shown)
        kept = self._shelf.read(identity)
        if kept:
            return kept
        body = None
        names = _poster_names(shown)
        for name in names:
            try:
                body = self._poster(name, shown.year or None, _kind(shown), _TIMEOUT)
            except Exception:
                continue
            if body:
                break
        if not body and shown.year and self._correct is not None:
            try:
                fixed = self._correct(names[0], shown.year, _kind(shown), _TIMEOUT)
                if fixed and fixed not in names:
                    body = self._poster(fixed, shown.year, _kind(shown), _TIMEOUT)
            except Exception:
                body = None
        if body:
            self._shelf.write(identity, body)
        return body


def _identity(shown: PlaybackSnapshot) -> str:
    """Чем картина отличается от соседки на полке: имя, год и её род."""
    return f"{shown.title}|{shown.year}|{_kind(shown)}"


def _key(shown: PlaybackSnapshot) -> str:
    """Чем один показ отличается от другого. Серия входит сюда, а в полку - нет.

    Постер у сериала один на все серии, и полка отвечает им на каждую. А вот запасной
    кадр - свой у каждой серии: на полку он не ложится, и брать его от прошлой серии
    значило бы показывать зрителю чужую картинку под видом этой.
    """
    return f"{_identity(shown)}|{shown.label}"


def _kind(shown: PlaybackSnapshot) -> str:
    """Сериал или фильм - тем же словом, каким род картины знает справка.

    Спрашивает его очередь имён статьи (:func:`titles_for`): у «Сталкера» уточнение
    «(телесериал)» и «(фильм)» ведут в разные статьи, и порядок решает, чей постер
    приедет. Подпись серии есть - это сериал; её ставит цикл показа, а не разбор имени.
    """
    return "tv" if shown.label else "movie"
