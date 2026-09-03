"""Картинки найденных картин для списка обзора: имя только тем, у кого картинка будет.

🔴 Имя выдаётся ПОСЛЕ приговора, а не до него. Раньше имя уносила каждая находка, и
маршрут ``/api/poster/`` отвечал потом «нет такой»: человек видел рамку вокруг пустоты
там, где строка должна была остаться строкой (TC-1023). Приговор - это вопрос «есть ли у
этой картины английская статья со сверенным годом»
(:meth:`~torrcast.adapters.wiki.poster_pages.PosterPages.wanted`), и стоит он на весь
список один-два запроса, а не по три на каждую находку.

Сами байты едут следом, фоном: пока Home Assistant рисует список и спрашивает картинки,
постеры обычно уже лежат. Найденное ложится на полку (:class:`hass.poster_shelf.PosterShelf`)
и второй раз берётся с неё, без сети вовсе. Полка общая с картинкой играющего
(:class:`hass.posters.Posters`), и это теперь честно: правило сверки года у них одно.

Промах откладывает следующий поход за той же картиной (:data:`_RETRY`), иначе список из
десяти находок стучал бы по Википедии на каждый заход в обзор.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from typing import Final

from hass.hit_ask import _about, _name
from hass.picture_type import picture_type
from hass.poster_shelf import PosterShelf
from hass.poster_source import PosterSource
from torrcast.adapters.wiki.wiki_poster import WikiPoster
from torrcast.domain.facts.ask import Ask
from torrcast.domain.json_value import JsonValue
from torrcast.runtime.facts_wiring import FACTS

#: Поле записи выдачи, в котором едет имя картинки. Его читает
#: :func:`custom_components.torrcast.browse.search_media`; нет поля - нет и картинки.
FIELD: Final = "poster"
#: Сколько ждём Википедию на один запрос, секунды.
_TIMEOUT: Final = 8.0
#: Через сколько секунд после промаха спрашиваем о той же картине снова.
_RETRY: Final = 300.0
#: Сколько ждёт запрос картинки, которая ещё в пути, секунды. Ждёт ОДИН запрос в своём
#: потоке сервера; ни снимок, ни показ этого ожидания не видят.
_WAIT: Final = 6.0
#: Сколько найденных картинок держим наготове: список находок бывает длинным.
_KEEP: Final = 64
#: Что известно про картинку находки к началу выдачи: готова, надо спрашивать, промах
#: ещё держится. Последнее НЕ равно первому: отложенный промах имени не даёт.
_READY: Final = "ready"
_ASK: Final = "ask"
_HELD: Final = "held"


class HitPosters:
    """Постеры списка находок: приговор на месте, картинки фоном."""

    def __init__(
        self,
        source: PosterSource | None = None,
        shelf: PosterShelf | None = None,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._source = source
        self._shelf = PosterShelf() if shelf is None else shelf
        self._now = now
        self._lock = threading.Lock()
        self._made: dict[str, bytes] = {}
        self._pending: dict[str, threading.Event] = {}
        self._tried: dict[str, float] = {}

    def offer(self, results: list[JsonValue]) -> list[JsonValue]:
        """Те же записи выдачи; имя картинки - только у тех, у кого картинка будет.

        Список этим задержан ровно на приговор: один-два запроса на всю пачку. Сами
        байты ждать нельзя - это уже секунды, и их человек ждал бы, глядя в пустое меню.
        """
        asks = [_about(record) for record in results]
        state = {ask: self._state(ask) for ask in dict.fromkeys(a for a in asks if a)}
        fresh = [ask for ask, one in state.items() if one is _ASK]
        ready = self._answer(fresh)
        found = {ask for ask, pages in ready.items() if pages}
        self._begin({ask: ready[ask] for ask in found})
        for ask in fresh:
            if ask not in found:
                with self._lock:
                    self._tried[_name(ask)] = self._now() + _RETRY
        known = found | {ask for ask, one in state.items() if one is _READY}
        return [
            {**record, FIELD: _name(ask)} if isinstance(record, dict) and ask in known else record
            for record, ask in zip(results, asks, strict=True)
        ]

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

    def _state(self, ask: Ask) -> str:
        """Что с картинкой этой картины: готова, надо спросить или промах ещё держится.

        Полка спрашивается тут же: снятая с неё картинка - это готовый ответ, и ходить
        за приговором о ней в сеть незачем. Отложенный промах - это НЕ готовность:
        имени такая находка не получает, иначе плитка снова осталась бы битой.
        """
        name = _name(ask)
        with self._lock:
            if name in self._made or name in self._pending:
                return _READY
            if self._now() < self._tried.get(name, 0.0):
                return _HELD
        kept = self._shelf.read(_name(ask))
        if not kept:
            return _ASK
        with self._lock:
            self._keep(name, kept)
        return _READY

    def _answer(self, asks: Sequence[Ask]) -> dict[Ask, list[str]]:
        """Приговор на всю пачку; сеть не ответила - считаем, что статей нет."""
        if not asks:
            return {}
        try:
            return self._source_of().wanted(asks, _TIMEOUT)
        except Exception:
            return {}

    def _begin(self, wanted: dict[Ask, list[str]]) -> None:
        """Пометить картинки как ожидаемые и уйти за их байтами фоном."""
        if not wanted:
            return
        with self._lock:
            for ask in wanted:
                self._pending[_name(ask)] = threading.Event()
        threading.Thread(target=self._fill, args=(wanted,), daemon=True, name="hit-posters").start()

    def _fill(self, wanted: dict[Ask, list[str]]) -> None:
        """Байты всей пачки разом и раздача их ждущим; промах - отложить попытку."""
        try:
            bodies = self._source_of().bodies(wanted, _TIMEOUT)
        except Exception:
            bodies = {}
        for ask in wanted:
            name, body = _name(ask), bodies.get(ask)
            if body:
                self._shelf.write(_name(ask), body)
            with self._lock:
                waiting = self._pending.pop(name, None)
                if body:
                    self._keep(name, body)
                else:
                    self._tried[name] = self._now() + _RETRY
            if waiting is not None:
                waiting.set()

    def _source_of(self) -> PosterSource:
        if self._source is None:
            self._source = WikiPoster(FACTS.client, FACTS.client)
        return self._source

    def _keep(self, name: str, body: bytes) -> None:
        """Положить картинку готовой, вытеснив самую давнюю, если их стало много."""
        self._made[name] = body
        while len(self._made) > _KEEP:
            self._made.pop(next(iter(self._made)))


#: Мост держит один список находок на всех: имя, выданное поиском, спрашивают потом
#: отдельным запросом за картинкой (:meth:`hass.posters.Posters.read`).
hits = HitPosters()
