"""Обложка играющей картины для пульта: полка отвечает сразу, сеть догоняет фоном."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Final

from hass.picture_source import picture_source
from hass.poster_lookup import _poster_asks, _poster_identity
from hass.poster_shelf import PosterShelf
from torrcast.domain.facts.ask import Ask
from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.runtime.playback_session import playback_session

#: Сколько ждём источник картинок на один запрос, секунды.
_TIMEOUT: Final = 8.0
#: Через сколько секунд после промаха пробуем снова. Промах бывает настоящим (статьи
#: нет) и временным (429, сеть легла), а различить их отсюда нечем; пульт же рисуется
#: каждые пару секунд, и без отсрочки промах превратился бы в стук по источникам.
_RETRY: Final = 300.0

_Poster = Callable[[Ask, float], bytes | None]


class PlayingPoster:
    """Байты обложки того, что играет; ещё не приехала - ``None``.

    Отвечает СРАЗУ и сеть не ждёт никогда: пульт рисуется на каждом тике наблюдателя
    (:class:`tgbot.playback_observer.PlaybackObserver`), и поход в Википедию на этом
    пути задержал бы кнопки на десятки секунд. Приехавшую обложку подберёт следующий
    тик, а не дождавшийся её пульт остаётся текстовым - с теми же кнопками.

    Картинка берётся тем же источником и с той же полки, что и карточка плеера
    (:class:`hass.posters.Posters`): разойдись они - в обзоре была бы одна обложка,
    а в пульте другая, причём молча.
    """

    def __init__(
        self,
        poster: _Poster | None = None,
        shelf: PosterShelf | None = None,
        shown: Callable[[], PlaybackSnapshot | None] | None = None,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._poster = poster
        self._shelf = PosterShelf() if shelf is None else shelf
        self._shown = shown or _playing
        self._now = now
        self._lock = threading.Lock()
        self._working: set[str] = set()
        self._tried: dict[str, float] = {}

    def __call__(self) -> bytes | None:
        """Обложка играющего с полки; её там нет - завести поход и ответить пустым."""
        shown = self._shown()
        if shown is None:
            return None
        identity = _poster_identity(shown)
        body = self._shelf.read(identity)
        if body:
            return body
        self._fetch(identity, shown)
        return None

    def _fetch(self, identity: str, shown: PlaybackSnapshot) -> None:
        """Завести фоновый поход за обложкой, если он не идёт и промах уже остыл."""
        with self._lock:
            since = self._tried.get(identity)
            if identity in self._working or (since is not None and self._now() - since < _RETRY):
                return
            self._working.add(identity)
        threading.Thread(
            target=self._bring, args=(identity, shown), daemon=True, name="telegram-poster"
        ).start()

    def _bring(self, identity: str, shown: PlaybackSnapshot) -> None:
        """Спросить источники и положить добытое на общую полку."""
        body: bytes | None = None
        with suppress(Exception):
            body = self._found(shown)
        with self._lock:
            self._working.discard(identity)
            self._tried[identity] = self._now()
        if body:
            self._shelf.write(identity, body)

    def _found(self, shown: PlaybackSnapshot) -> bytes | None:
        """Первая обложка из имён картины по порядку доверия к ним."""
        poster = self._poster or picture_source().poster
        for ask in _poster_asks(shown):
            body = poster(ask, _TIMEOUT)
            if body:
                return body
        return None


def _playing() -> PlaybackSnapshot | None:
    """Снимок живого показа; показа нет - ``None``."""
    session = playback_session()
    if not session.active():
        return None
    return session.snapshot(session.key())
