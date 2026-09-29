"""Два источника картинок: спокойный путь бережёт Википедию, срочный не ждёт её молча.

Порядок тут не про вкус, а про доверие. Обложка в статье Википедии - это обложка ИМЕННО
той картины, про которую статья, со сверенным годом выхода; подсказчик IMDb ранжирует по
популярности и тёзку от тёзки отличает только годом. Поэтому спокойный путь спрашивает
второй только о промахах первого, а срочный открывает его параллельно и берёт ранний,
проверенный ответ, когда Википедия задержалась.

Байты у обоих одни: приговор - готовый адрес файла, а плитку без байт добирают адреса
проигравшего в той же гонке (:mod:`hass.spare_bodies`), зависший хост её не обнуляет.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence

from hass.poster_race import PosterRace
from hass.poster_source import PosterSource
from hass.spare_bodies import spare_bodies
from torrcast.adapters.wiki.poster_bodies import PosterBodies
from torrcast.domain.facts.ask import Ask
from torrcast.ports.bytes_client import BytesClient

#: Видимый ряд недолго ждёт более надёжную Википедию, затем берёт уже проверенный IMDb.
_URGENT_BY = 1.5
#: How many source timeouts the late landing waits for a race it inherited.
_LATE_BY = 3
#: How many visible asks keep their race for spare addresses; the oldest are dropped first.
_RACES_KEPT = 512


class BothPosters:
    """Приговор первого источника, а на промолчавших - приговор второго."""

    def __init__(
        self, first: PosterSource, second: PosterSource, files: BytesClient, *, urgent: bool = False
    ) -> None:
        self.first = first
        self.second = second
        self.pictures = PosterBodies(files)
        self.urgent = urgent
        self._lock = threading.Lock()
        #: Visible asks whose race is still on the wire: the late landing waits for it.
        self._racing: dict[Ask, PosterRace] = {}
        #: The race each visible ask was served by, the loser's answer included.
        self._raced: dict[Ask, PosterRace] = {}

    def poster(self, ask: Ask, timeout: float) -> bytes | None:
        """Байты постера одной картины; постера у неё нет ни там, ни там - ``None``.

        Дверь карточки играющего идёт теми же двумя источниками, что и список обзора, и
        это обязательно: полка у них общая, и разойдись правила - человек увидел бы в
        списке одну картинку, а на экране другую.
        """
        return self.bodies(self.wanted([ask], timeout), timeout).get(ask)

    def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
        """Адреса постеров: первый надёжнее, а в видимом ряду второй не стоит за его сетью.

        Спокойный путь спрашивает второй источник только для промахов первого. Срочный
        запускает оба: внешний ответ первого может занять секунды, а плитка не должна
        ждать, когда второй уже назвал точный постер. Если первый успел первым, он всё
        равно оставляет второй только свои промахи.

        🔴 Обрыв второго не стирает ответ первого: найденное первым остаётся. Но картины,
        о которых второй промолчал, в ответ НЕ попадают вовсе: отказ источника - это
        «неизвестно», а не «картинки нет» (:mod:`hass.hit_posters` спросит их снова).
        Пустой список значит одно: ответили все, кого спрашивали, и картинки нет.
        """
        return self._urgent(asks, timeout) if self.urgent else self._after_first(asks, timeout)

    def _after_first(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
        found = self.first.wanted(asks, timeout)
        left = [ask for ask in asks if not found.get(ask)]
        if not left:
            return found
        try:
            more = self.second.wanted(left, timeout)
        except Exception:
            return {ask: found[ask] for ask in asks if found.get(ask)}
        return {ask: found.get(ask) or more.get(ask, []) for ask in asks}

    def _urgent(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
        """Race the sources once; an overdue source is unknown, not a missing poster.

        A source handing pictures one by one ends the wait at its first hit; the rest lands late.
        """
        each = getattr(self.second, "wanted_each", None)
        race = PosterRace(
            lambda _heard: self.first.wanted(asks, timeout),
            lambda heard: (
                each(asks, timeout, heard) if callable(each) else self.second.wanted(asks, timeout)
            ),
        )
        deadline = time.monotonic() + _URGENT_BY
        race.wait(deadline, lambda: race.over() or any(race.said(asks).values()))
        said = race.said(asks)
        with self._lock:
            self._racing.update({ask: race for ask in asks if ask not in said})
            for ask in asks:
                self._raced.pop(ask, None)
                self._raced[ask] = race
            while len(self._raced) > _RACES_KEPT:
                del self._raced[next(iter(self._raced))]
        return said

    def finish_urgent(
        self, asks: Sequence[Ask], timeout: float, land: Callable[[dict[Ask, list[str]]], None]
    ) -> dict[Ask, list[str]]:
        """Wait for the answers the visible race left in flight; land each hit as it comes.

        The sources are not asked again: their requests are already on the wire, and a new
        round would put the row behind the background queue and pay the network twice.
        """
        with self._lock:
            races = {ask: self._racing.pop(ask, None) for ask in asks}
        cold = [ask for ask, race in races.items() if race is None]
        said = self._after_first(cold, timeout) if cold else {}
        if any(said.values()):
            land({ask: pages for ask, pages in said.items() if pages})
        for race in {race for race in races.values() if race is not None}:
            mine = [ask for ask in asks if races[ask] is race]
            said.update(race.land(mine, time.monotonic() + _LATE_BY * timeout, land))
        return said

    def bodies(self, wanted: dict[Ask, list[str]], timeout: float) -> dict[Ask, bytes]:
        """Байты по названным адресам; зависший хост отдаёт плитку адресам другого источника.

        Запасные адреса берутся только из гонки видимого ряда, где ответ проигравшего уже
        оплачен. Спокойный путь второй источник об удачах первого не спрашивал, и запаса у
        него нет: новый запрос к API ради запаса здесь не делается никогда.
        """

        def spare(ask: Ask) -> list[str]:
            with self._lock:
                race = self._raced.get(ask)
            return race.spare(ask, time.monotonic() + timeout) if race is not None else []

        return spare_bodies(self.pictures, spare, wanted, timeout)
