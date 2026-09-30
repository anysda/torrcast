"""Что мост знает о картинке каждой картины: готова, в пути, отложена или заявлена.

Заявка - это приговор, который уже идёт: второй спросивший о той же картине ждёт его, а не
зовёт свой. Без неё превью и финал поиска судили одну выдачу дважды, и сторож
«повтор не судит известное» падал 5 раз из 40.

Промахов два. Настоящий (источник ответил, картинки нет) держится :data:`_RETRY`. Пустой
ответ в минуту 429 или отказа по счёту - не ответ: картину спросят снова, когда тишина
кончится, но не больше :data:`_ATTEMPTS` раз подряд, иначе источник, лежащий час, стоил бы
запроса на каждую сборку полок.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from typing import Final

from hass.hit_ask import _about, _name
from hass.poster_shelf import PosterShelf
from torrcast.domain.facts.ask import Ask
from torrcast.domain.json_value import JsonValue

#: Через сколько секунд после промаха спрашиваем о той же картине снова.
_RETRY: Final = 300.0
#: Сколько раз подряд картину спрашивают после пустого ответа в минуту отказов.
_ATTEMPTS: Final = 3
#: Сколько ждёт запрос картинки, которая ещё в пути, секунды. Ждёт ОДИН запрос в своём
#: потоке сервера; ни снимок, ни показ этого ожидания не видят.
_WAIT: Final = 6.0
#: Сколько найденных картинок держим наготове: список находок бывает длинным.
_KEEP: Final = 64
#: Что известно про картинку к началу выдачи: готова, надо спрашивать (и заявка теперь
#: наша), промах ещё держится, приговор уже идёт у другого. Держащийся промах НЕ равен
#: готовой: отложенный промах имени не даёт.
_READY: Final = "ready"
_ASK: Final = "ask"
_HELD: Final = "held"
_CLAIMED: Final = "claimed"
#: Приговор идёт у спокойного пути (история, полки, «похожие»), а спрашивает видимый ряд: он
#: не ждёт чужую очередь за Википедией по 8-14 с, а судит картину и сам, своей гонкой. Один
#: раз на заявку: следующий показ того же ряда получает :data:`_HELD` и не ждёт.
_BESIDE: Final = "beside"


class HitClaims:
    """Память картинок находок под одним замком."""

    def __init__(self, shelf: PosterShelf, now: Callable[[], float] = time.monotonic) -> None:
        self._shelf = shelf
        self._now = now
        self._lock = threading.Lock()
        self._made: dict[str, bytes] = {}
        self._pending: dict[str, threading.Event] = {}
        self._tried: dict[str, float] = {}
        self._again: dict[str, tuple[int, float]] = {}
        self._judging: dict[str, threading.Event] = {}
        #: Заявки спокойного пути -> видимый ряд уже судил картину рядом (один раз на заявку).
        self._calm: dict[str, bool] = {}
        self._late_names: set[str] = set()
        self._landed: set[str] = set()

    def named(self, name: str) -> bool:
        """Имя картинки можно выдавать: байты здесь или уже едут."""
        with self._lock:
            return self._holds(name)

    def has(self, name: str) -> bool:
        """Байты картинки лежат здесь или на полке, и маршрут отдаст их без ожидания."""
        with self._lock:
            return name in self._made or name in self._landed

    def coming(self, name: str) -> bool:
        """Картинка ещё может приехать: приговор или байты в пути, повтор впереди."""
        with self._lock:
            return (
                name in self._judging
                or name in self._pending
                or name in self._again
                or name in self._late_names
            )

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

    def ripe(self, name: str) -> bool:
        """Отложенный из-за отказов приговор пора спросить снова, и никто его не спрашивает."""
        with self._lock:
            again = self._again.get(name)
            return again is not None and name not in self._judging and self._now() >= again[1]

    def _claim(self, asks: Sequence[Ask], urgent: bool = False) -> dict[Ask, str]:
        """Состояние каждой картины; незаявленные и неизвестные заявляются за спросившим.

        Пачка заявляется одним проходом под замком: по картине за раз превью и финал делили
        одну выдачу пополам и звали источник дважды. Полка читается после, вне замка; что
        нашлось на ней, снимается с заявки готовым.
        """
        with self._lock:
            state = {ask: self._known(_name(ask), urgent) for ask in asks}
            for ask, one in state.items():
                if one is _BESIDE or (one is _ASK and not urgent):
                    self._calm[_name(ask)] = one is _BESIDE
                if one is _ASK:
                    self._judging[_name(ask)] = threading.Event()
        for ask in [ask for ask, one in state.items() if one is _ASK]:
            name = _name(ask)
            kept = self._shelf.read(name)
            if not kept:
                continue
            with self._lock:
                self._keep(name, kept)
                self._calm.pop(name, None)
                event = self._judging.pop(name)
            state[ask] = _READY
            event.set()
        return state

    def _known(self, name: str, urgent: bool = False) -> str:
        if self._holds(name):
            return _READY
        if name in self._judging:
            if not urgent or name not in self._calm:
                return _CLAIMED
            return _HELD if self._calm[name] else _BESIDE
        if name in self._late_names:
            return _HELD
        now = self._now()
        if now < self._tried.get(name, 0.0) or now < self._again.get(name, (0, 0.0))[1]:
            return _HELD
        return _ASK

    def _release(self, asks: Sequence[Ask]) -> None:
        """Снять заявки: ждущие их просыпаются и читают вынесенный приговор."""
        with self._lock:
            events = [self._judging.pop(_name(ask), None) for ask in asks]
            for ask in asks:
                self._calm.pop(_name(ask), None)
        for event in events:
            if event is not None:
                event.set()

    def _holds(self, name: str) -> bool:
        """Под замком: байты картины здесь или уже едут."""
        return name in self._made or name in self._pending or name in self._landed

    def _missed(self, name: str, unknown: bool, calm_at: float) -> None:
        """Промах под замком: настоящий держится долго, неизвестный - до тишины; легшей нет."""
        if name in self._made or name in self._landed:
            return
        if unknown and self._now() < self._tried.get(name, 0.0):
            return  # настоящий промах в силе: молчание другого судьи его не отменяет
        tries = self._again.get(name, (0, 0.0))[0] + 1
        if unknown and tries < _ATTEMPTS:
            self._again[name] = (tries, calm_at)
            return
        self._again.pop(name, None)
        self._tried[name] = self._now() + _RETRY

    def _keep(self, name: str, body: bytes) -> None:
        """Положить картинку готовой, вытеснив самую давнюю, если их стало много."""
        self._landed.add(name)
        self._again.pop(name, None)
        self._made[name] = body
        while len(self._made) > _KEEP:
            self._made.pop(next(iter(self._made)))


__all__ = ["HitClaims"]
