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
from hass.hit_book import hit_book
from hass.hit_claims import _ASK, _BESIDE, _CLAIMED, _KEEP, _RETRY, _WAIT, HitClaims
from hass.late_posters import late_posters
from hass.picture_source import picture_source
from hass.picture_type import picture_type
from hass.poster_parts import poster_parts
from hass.poster_shelf import PosterShelf
from hass.poster_source import PosterSource
from hass.serial_parent_posters import _ready_posters, serial_parent_posters
from hass.wait_each import wait_each
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
        self._sources = dict.fromkeys(("calm", "urgent", "ahead"), source)
        self._weather = weather or (FactsWeather() if source is None else _CalmWeather())

    def offer(
        self, results: list[JsonValue], urgent: bool = False, ahead: bool = False
    ) -> list[JsonValue]:
        """Те же записи выдачи; имя картинки - только у тех, у кого картинка будет.

        Список этим задержан ровно на приговор: один-два запроса на всю пачку. Сами
        байты ждать нельзя - это уже секунды, и их человек ждал бы, глядя в пустое меню.
        Приговор о той же картине, уже идущий у другого, ждётся, а не зовётся второй раз.
        """
        asks = [_about(record) for record in results]
        state = self._claim(list(dict.fromkeys(a for a in asks if a)), urgent)
        fresh = [ask for ask, one in state.items() if one is _ASK]
        try:
            beside = [ask for ask, one in state.items() if one is _BESIDE]
            self._judge(fresh, urgent, beside, ahead=ahead)
        finally:
            self._release(fresh)
        claimed = [_name(ask) for ask, one in state.items() if one is _CLAIMED]
        wait_each(self._lock, self._judging, claimed, _TIMEOUT + 1.0)
        known = {ask for ask in state if self.named(_name(ask))}
        return [
            {**record, FIELD: _name(ask)} if isinstance(record, dict) and ask in known else record
            for record, ask in zip(results, asks, strict=True)
        ]

    def urgent(self, results: list[JsonValue]) -> list[JsonValue]:
        """Приговор видимого списка; байты едут следом без задержки выдачи.

        Имя остаётся в записи до следующего опроса. Страница отдаёт его только после
        приземления байтов и меняет картинку в уже стоящей плитке, не перестраивая ряд.
        """
        return serial_parent_posters(self.offer(results, urgent=True), self.has)

    def settled(self, results: list[JsonValue]) -> list[JsonValue]:
        """:meth:`offer` фоновой сборки: имя остаётся только у тех, чьи байты уже легли.

        Полку главной страница получает готовой, и имя без байтов держало соединение
        браузера на маршруте картинки до :data:`~hass.hit_claims._WAIT`: шесть таких плиток
        останавливали опрос поиска на той же вкладке (TC-1286). Байты ждёт фон, а не человек.
        """
        offered = self.offer(results)
        names = [_name(ask) for ask in map(_about, offered) if ask]
        wait_each(self._lock, self._pending, names, _SETTLE_BY)
        return _ready_posters(serial_parent_posters(offered, self.has), self.has)

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

    def _judge(
        self, fresh: list[Ask], urgent: bool, beside: Sequence[Ask] = (), ahead: bool = False
    ) -> None:
        """Приговор пачке заявленных картин; ответ в минуту отказов - не промах.

        Картины, о которых источник промолчал (нет в ответе), - не промах: видимый ряд
        дожидается их уже идущих запросов (:mod:`hass.late_posters`), остальные спросят снова.
        ``beside`` - картины чужого спокойного приговора, которые видимый ряд судит и сам.
        """
        asked = [*fresh, *beside]
        if not asked:
            return
        began = self._now()
        said = self._answer(asked, self._source_of(urgent, ahead))
        troubled = said is None or self._weather.troubled_since(began)
        late = getattr(self._source_of(urgent), "finish_urgent", None) if urgent else None
        later = [ask for ask in asked if callable(late) and ask not in (said or {})]
        found = hit_book(self, asked, said, later, beside, troubled, self._weather.calm_at())
        if found:
            threading.Thread(target=self._fill, args=(found, urgent, ahead), daemon=True).start()
        if later:
            threading.Thread(
                target=late_posters, args=(self, later, late, _TIMEOUT), daemon=True
            ).start()

    def _answer(self, asks: Sequence[Ask], source: PosterSource) -> dict[Ask, list[str]] | None:
        """Приговор на всю пачку; ``None`` - источник МОЛЧИТ, а не «постеров нет»."""
        try:
            return source.wanted(asks, _TIMEOUT)
        except Exception:
            return None

    def _fill(self, wanted: dict[Ask, list[str]], urgent: bool, ahead: bool = False) -> None:
        """Байты пачки частями (:mod:`hass.poster_parts`): доехавшая ложится, не ждя медленной."""
        poster_parts(wanted, lambda part: self._land(part, urgent, ahead))

    def _land(self, wanted: dict[Ask, list[str]], urgent: bool, ahead: bool = False) -> None:
        """Байты одной части и раздача их ждущим.

        Приговор уже назвал адрес, и байты не доехали - источник промолчал (обрыв чтения у
        IMDb), а не «картинки нет»: спросить снова, не больше :data:`~hass.hit_claims._ATTEMPTS`.
        """
        try:
            bodies = self._source_of(urgent, ahead).bodies(wanted, _TIMEOUT)
        except Exception:
            bodies = {}
        for ask in wanted:
            name, body = _name(ask), bodies.get(ask)
            if body:
                self._shelf.write(name, body)
            with self._lock:
                waiting = self._pending.pop(name, None)
                if body:
                    self._keep(name, body)
                else:
                    self._missed(name, True, self._weather.calm_at())
            if waiting is not None:
                waiting.set()

    def _source_of(self, urgent: bool = False, ahead: bool = False) -> PosterSource:
        kind = "urgent" if urgent else "ahead" if ahead else "calm"
        made = self._sources[kind] or picture_source(**({} if kind == "calm" else {kind: True}))
        self._sources[kind] = made
        return made


#: Мост держит один список находок на всех: имя, выданное поиском, спрашивают потом
#: отдельным запросом за картинкой (:meth:`hass.posters.Posters.read`).
hits = HitPosters()

__all__ = ["FIELD", "_KEEP", "_RETRY", "_WAIT", "HitPosters", "hits"]
