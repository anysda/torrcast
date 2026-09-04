"""Картинка играющей картины для карточки плеера: кадр показа сразу, постер следом."""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from typing import Final

from hass.hit_posters import hits
from hass.picture_source import picture_source
from hass.picture_type import picture_type
from hass.poster_find import poster_find
from hass.poster_lookup import _frame_key, _manifest, _playing_key, _poster_asks, _poster_identity
from hass.poster_shelf import PosterShelf
from torrcast.adapters.ffmpeg.frame_shot import frame_shot
from torrcast.domain.facts.ask import Ask
from torrcast.domain.playback_snapshot import PlaybackSnapshot

#: Начало адреса картинки на серве. Наружу за ней Home Assistant не ходит НИКОГДА:
#: постер скачивает себе серв, а карточке отдаёт своим маршрутом в локальной сети.
#: Иначе картинку тянул бы клиент - через ту самую сеть, где режут по SNI.
ROUTE: Final = "/api/poster/"
#: Сколько ждём источник картинок на один запрос, секунды.
_TIMEOUT: Final = 8.0
#: Через сколько секунд после промаха пробуем снова. Промах бывает и настоящим (статьи
#: нет), и временным (429, сеть легла), а различить их отсюда нечем. Поэтому не «никогда
#: больше», но и не «на каждый опрос»: карточку опрашивают раз в несколько секунд, и без
#: этой отсрочки промах превратился бы в ровный стук по источникам на весь показ.
_RETRY: Final = 300.0
#: Сколько картинок держим наготове. Больше одной - чтобы карточка не осталась без
#: байтов ровно в тот миг, когда показ уже сменился, а Home Assistant ещё тянет прошлую.
#: Показ оставляет по ДВЕ: кадр и сменивший его постер, и обеих спрашивают наружу.
_KEEP: Final = 8
#: Через сколько пробуем кадр снова и сколько раз всего, секунды и попытки.
#: 🔴 Одной попытки НЕ ХВАТАЕТ, и замер это показал: сетка раздачи открывается ffmpeg
#: только на 4.3 с показа, а первый опрос карточки приходит на 2 с - ровно туда, где
#: манифеста ещё нет. Единственная попытка промахивалась мимо готовности на пару секунд,
#: и карточка стояла пустой ВСЁ время показа (118 с замера, дальше - до конца отсрочки).
_AGAIN: Final = 2.0
_SHOTS: Final = 20

_Poster = Callable[[Ask, float], bytes | None]
_Frame = Callable[[str], bytes | None]
_Stream = Callable[[], str]


class Posters:
    """Картинка того, что играет: кадр показа сразу, а постер из сети - когда приедет.

    Работа идёт ФОНОМ, а снимок отвечает тем, что уже готово. Снимок серва спрашивают
    раз в несколько секунд, и ждать в нём похода в сеть нельзя: карточка плеера
    замерла бы на всё время ожидания, а вместе с ней замерли бы полоса времени и пульт.

    🔴 Кадр снимается НЕ ВМЕСТО постера и не после его провала, а рядом с ним, с первой
    же секунды показа. Постер едет из сети до полуминуты: два имени картины, два
    источника, восемь секунд сроку на запрос, - и всё это время карточка стояла пустой,
    хотя кадр собственной раздачи готов за пару секунд. Внешними источниками пустота не
    лечится в принципе: у Википедии потолок 55%, у IMDb 76.4%, а кадр есть всегда, пока
    идёт показ. Приехавший постер кадр сменит - отпечаток у него свой.

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
        pause: Callable[[float], None] = time.sleep,
    ) -> None:
        source = picture_source()
        self._poster = poster or source.poster
        self._frame = frame
        self._shelf = PosterShelf() if shelf is None else shelf
        self._now = now
        self._pause = pause
        self._lock = threading.Lock()
        self._made: dict[str, tuple[str, bytes]] = {}
        self._working: set[str] = set()
        self._tried: dict[str, float] = {}

    def picture(self, shown: PlaybackSnapshot | None, stream: _Stream) -> tuple[str, str]:
        """Адрес картинки на серве и её отпечаток; готовой ещё нет - две пустых строки.

        Постер спрашивается ПЕРЕД кадром, и это единственное место, где решается их
        старшинство: пока постера нет, отвечает кадр, а появился - и карточка берёт его,
        не дожидаясь следующего показа.

        Адрес раздачи спрашивается ССЫЛКОЙ, а не значением: собирать его на каждый опрос
        ради картинки, которая уже готова, незачем - а опрашивают карточку весь показ.
        """
        if shown is None or not shown.title:
            return "", ""
        key = _playing_key(shown)
        with self._lock:
            made = self._made.get(key) or self._made.get(_frame_key(key))
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

        Маршрут один на все картинки серва, поэтому за играющей картиной спрашивается и
        список находок (:class:`hass.hit_posters.HitPosters`): имена там свои, но дверь
        наружу общая.
        """
        with self._lock:
            for made, body in self._made.values():
                if made == name:
                    return body, picture_type(body)
        return hits.read(name)

    def _resolve(self, key: str, shown: PlaybackSnapshot, stream: _Stream) -> None:
        """Снять кадр показа и найти постер; нет ни того, ни другого - отложить попытку.

        Полка спрашивается ПЕРВОЙ и отвечает мгновенно: постер этой картины уже лежит на
        диске, и снимать под него кадр значило бы гонять ffmpeg на каждую серию ради
        картинки, которую всё равно никто не увидит.
        """
        identity = _poster_identity(shown)
        kept = self._shelf.read(identity)
        if kept is None:
            self._meanwhile(key, stream)
        body = kept or self._sought(shown, identity)
        with self._lock:
            self._working.discard(key)
            if body:
                self._keep(key, body)
            elif _frame_key(key) not in self._made:
                self._tried[key] = self._now() + _RETRY

    def _sought(self, shown: PlaybackSnapshot, identity: str) -> bytes | None:
        """Постер из сети, и найденный - на полку. Источники молчат - постера нет.

        Сам поход - общий с картинками списка находок (:func:`hass.poster_find.poster_find`):
        одно правило на обоих, иначе под одним именем приехали бы две разных картинки.
        """
        body = poster_find(_poster_asks(shown), _TIMEOUT, self._poster)
        if body:
            self._shelf.write(identity, body)
        return body

    def _meanwhile(self, key: str, stream: _Stream) -> None:
        """Пока постер едет из сети, снять кадр показа - своим потоком, не задерживая.

        Адреса раздачи может не быть вовсе: у оборванного показа на его месте стоит
        фраза для человека, а не ссылка
        (:meth:`~torrcast.adapters.unit_playback_session.UnitPlaybackSession.stream_address`).
        Тогда кадра не будет, и карточка дождётся одного лишь постера.
        """
        where = stream()
        if not where.startswith("http"):
            return
        threading.Thread(
            target=self._shot, args=(key, _manifest(where)), daemon=True, name="frame"
        ).start()

    def _shot(self, key: str, source: str) -> None:
        """Кадр показа - на своё место, и пробуем, пока сетка раздачи не откроется.

        🔴 Промах тут значит «ЕЩЁ рано», а не «кадра не будет»: показ объявляется
        играющим раньше, чем ffmpeg может прочитать манифест, и первая попытка приходится
        ровно на эту щель. Одна попытка оставляла карточку пустой на весь показ, потому
        что второй ей взяться было неоткуда: постер уже промахнулся и отложил себя на
        :data:`_RETRY`, а кадр не пробовал больше никто.
        """
        for attempt in range(_SHOTS):
            if attempt:
                self._pause(_AGAIN)
            body = self._frame(source)
            if body:
                with self._lock:
                    self._keep(_frame_key(key), body)
                return

    def _keep(self, key: str, body: bytes) -> None:
        """Положить картинку готовой под её отпечатком; замок держит зовущий."""
        self._made[key] = (hashlib.sha256(body).hexdigest()[:16], body)
        while len(self._made) > _KEEP:
            self._made.pop(next(iter(self._made)))
