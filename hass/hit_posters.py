"""Картинки найденных картин для списка обзора: имя только тем, у кого картинка будет.

🔴 Имя выдаётся ПОСЛЕ приговора, а не до него. Раньше имя уносила каждая находка, и
маршрут ``/api/poster/`` отвечал потом «нет такой»: человек видел рамку вокруг пустоты
там, где строка должна была остаться строкой (TC-1023). Приговор - это готовый АДРЕС
файла постера (:meth:`~torrcast.adapters.wiki.wiki_poster.WikiPoster.wanted`), и стоит
он на весь список полдесятка запросов, а не по три на каждую находку.

🔴 Адрес, а не имя статьи, - и это разница между «рамка бывает битой» и «не бывает».
Приговор по статье отвечал «да» и той картине, у которой статья есть, а обложки в ней
нет: имя картинки уезжало в выдачу, а байтов за ним не было никогда.

Сами байты едут следом, фоном, и ложатся на полку (:class:`hass.poster_shelf.PosterShelf`),
общую с картинкой играющего (:class:`hass.posters.Posters`).

Приговор о картине идёт ОДИН на всех: превью, финал поиска и полки, спросившие о той же
картине, пока он в пути, ждут его, а не зовут второй (:mod:`hass.hit_claims`). Промах
откладывает следующий поход на :data:`~hass.hit_claims._RETRY`; пустой ответ в минуту 429
или отказа по счёту промахом не считается и спрашивается снова, когда тишина кончится.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence

from hass.facts_weather import FactsWeather, _CalmWeather, _Weather
from hass.hit_ask import _about, _name
from hass.hit_claims import _ASK, _CLAIMED, _KEEP, _RETRY, _WAIT, HitClaims
from hass.picture_source import picture_source
from hass.picture_type import picture_type
from hass.poster_parts import poster_parts
from hass.poster_shelf import PosterShelf
from hass.poster_source import PosterSource
from torrcast.domain.facts.ask import Ask
from torrcast.domain.json_value import JsonValue

#: Поле записи выдачи, в котором едет имя картинки. Его читает
#: :func:`custom_components.torrcast.search_media.search_media`; нет поля - нет и картинки.
FIELD = "poster"
#: Сколько ждём источник картинок на один запрос, секунды.
_TIMEOUT = 8.0
#: Сколько фоновая сборка ждёт байты всей своей пачки, секунды.
_SETTLE_BY = 30.0


class HitPosters(HitClaims):
    """Постеры списка находок: приговор на месте, картинки фоном."""

    def __init__(
        self,
        source: PosterSource | None = None,
        shelf: PosterShelf | None = None,
        now: Callable[[], float] = time.monotonic,
        weather: _Weather | None = None,
    ) -> None:
        super().__init__(PosterShelf() if shelf is None else shelf, now)
        self._source = source
        self._urgent_source = source
        self._weather = weather or (FactsWeather() if source is None else _CalmWeather())

    def offer(self, results: list[JsonValue], urgent: bool = False) -> list[JsonValue]:
        """Те же записи выдачи; имя картинки - только у тех, у кого картинка будет.

        Список этим задержан ровно на приговор: один-два запроса на всю пачку. Сами
        байты ждать нельзя - это уже секунды, и их человек ждал бы, глядя в пустое меню.
        Приговор о той же картине, уже идущий у другого, ждётся, а не зовётся второй раз.
        """
        asks = [_about(record) for record in results]
        state = self._claim(list(dict.fromkeys(a for a in asks if a)))
        fresh = [ask for ask, one in state.items() if one is _ASK]
        try:
            self._judge(fresh, urgent)
        finally:
            self._release(fresh)
        self._await([ask for ask, one in state.items() if one is _CLAIMED], _TIMEOUT + 1.0)
        known = {ask for ask in state if self.named(_name(ask))}
        return [
            {**record, FIELD: _name(ask)} if isinstance(record, dict) and ask in known else record
            for record, ask in zip(results, asks, strict=True)
        ]

    def urgent(self, results: list[JsonValue]) -> list[JsonValue]:
        """:meth:`offer` видимого списка: его запросы идут впереди полок и «похожих»."""
        return self.offer(results, urgent=True)

    def settled(self, results: list[JsonValue]) -> list[JsonValue]:
        """:meth:`offer` фоновой сборки: имя остаётся только у тех, чьи байты уже легли.

        Полку главной страница получает готовой, и имя без байтов держало соединение
        браузера на маршруте картинки до :data:`~hass.hit_claims._WAIT`: шесть таких плиток
        останавливали опрос поиска на той же вкладке (TC-1286). Байты ждёт фон, а не человек.
        """
        offered = self.offer(results)
        self._arrive([_name(ask) for ask in map(_about, offered) if ask], _SETTLE_BY)
        return [
            {name: value for name, value in record.items() if name != FIELD}
            if isinstance(record, dict) and FIELD in record and not self.landed(record)
            else record
            for record in offered
        ]

    def landed(self, record: JsonValue) -> bool:
        """Байты картинки этой записи уже здесь: плитка не ждёт их на маршруте."""
        ask = _about(record)
        return ask is not None and self.has(_name(ask))

    def pending(self, records: Sequence[JsonValue]) -> bool:
        """У кого-то из записей картинка ещё может приехать: приговор, байты или повтор."""
        return any(ask is not None and self.coming(_name(ask)) for ask in map(_about, records))

    def due(self, records: Sequence[JsonValue]) -> bool:
        """Кому-то из записей пора спросить приговор снова: тишина источника кончилась."""
        return any(ask is not None and self.ripe(_name(ask)) for ask in map(_about, records))

    def read(self, name: str) -> tuple[bytes, str] | None:
        """Байты картинки и её тип; она ещё в пути - подождать, но не бесконечно.

        Список этим не задержан: он ушёл человеку раньше, и ждёт картинку браузер.

        🔴 Полка спрашивается последней, и без неё плитка оставалась битой при живых
        байтах на диске (TC-1029): имя выдаётся по полке, а память моста короче списка.
        """
        with self._lock:
            body = self._made.get(name)
            waiting = None if body else self._pending.get(name)
        if body is None and waiting is not None:
            waiting.wait(_WAIT)
            with self._lock:
                body = self._made.get(name)
        body = body or self._shelf.read(name)
        return (body, picture_type(body)) if body else None

    def _judge(self, fresh: list[Ask], urgent: bool) -> None:
        """Приговор пачке заявленных картин; ответ в минуту отказов - не промах."""
        if not fresh:
            return
        began = self._now()
        answered = self._answer(fresh, urgent)
        troubled = answered is None or self._weather.troubled_since(began)
        found = {ask: pages for ask, pages in (answered or {}).items() if pages and ask in fresh}
        with self._lock:
            for ask in fresh:
                if ask in found:
                    self._pending[_name(ask)] = threading.Event()
                else:
                    self._missed(_name(ask), troubled, self._weather.calm_at())
        if found:
            threading.Thread(target=self._fill, args=(found, urgent), daemon=True).start()

    def _answer(self, asks: Sequence[Ask], urgent: bool) -> dict[Ask, list[str]] | None:
        """Приговор на всю пачку; ``None`` - источник МОЛЧИТ, а не «постеров нет»."""
        try:
            return self._source_of(urgent).wanted(asks, _TIMEOUT)
        except Exception:
            return None

    def _fill(self, wanted: dict[Ask, list[str]], urgent: bool) -> None:
        """Байты пачки частями (:mod:`hass.poster_parts`): доехавшая ложится, не ждя медленной."""
        poster_parts(wanted, lambda part: self._land(part, urgent))

    def _land(self, wanted: dict[Ask, list[str]], urgent: bool) -> None:
        """Байты одной части и раздача их ждущим; промах - отложить попытку."""
        began = self._now()
        failed = False
        try:
            bodies = self._source_of(urgent).bodies(wanted, _TIMEOUT)
        except Exception:
            bodies, failed = {}, True
        troubled = failed or self._weather.troubled_since(began)
        for ask in wanted:
            name, body = _name(ask), bodies.get(ask)
            if body:
                self._shelf.write(name, body)
            with self._lock:
                waiting = self._pending.pop(name, None)
                if body:
                    self._keep(name, body)
                else:
                    self._missed(name, troubled, self._weather.calm_at())
            if waiting is not None:
                waiting.set()

    def _source_of(self, urgent: bool = False) -> PosterSource:
        if urgent:
            if self._urgent_source is None:
                self._urgent_source = picture_source(urgent=True)
            return self._urgent_source
        if self._source is None:
            self._source = picture_source()
        return self._source


#: Мост держит один список находок на всех: имя, выданное поиском, спрашивают потом
#: отдельным запросом за картинкой (:meth:`hass.posters.Posters.read`).
hits = HitPosters()

__all__ = ["FIELD", "_KEEP", "_RETRY", "_WAIT", "HitPosters", "hits"]
