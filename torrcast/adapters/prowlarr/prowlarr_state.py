"""Поля клиента одного поиска и мелкие справки по ним: бюджеты, молчуны, остаток цели.

Наследует их :class:`torrcast.adapters.prowlarr.prowlarr.Prowlarr`, и только он."""

from __future__ import annotations

import time
from collections.abc import Callable

from torrcast.adapters.prowlarr.indexer_circle import ASK_SLACK, IndexerCircle
from torrcast.adapters.prowlarr.indexer_roster import IndexerRoster, _aside, _Spawn
from torrcast.adapters.prowlarr.prowlarr_api import TIMEOUT, ProwlarrApi
from torrcast.domain.circle_budget import FIRST_CIRCLE_TIMEOUT
from torrcast.domain.goal_spare import CIRCLE_SHARE, goal_spare
from torrcast.domain.indexer_budget import indexer_budget


class _State:
    """Всё, что клиент про себя знает: свои бюджеты, свой счёт молчунов, свой остаток цели."""

    def __init__(
        self,
        base_url: str,
        apikey: str,
        timeout: float = TIMEOUT,
        *,
        slack: float = ASK_SLACK,
        budget_of: Callable[[str], float] = indexer_budget,
        heal: _Spawn = _aside,
    ) -> None:
        self._api = ProwlarrApi(base_url, apikey, timeout)
        self.base_url = self._api.base_url
        self.apikey = self._api.apikey
        self.timeout = timeout
        #: Чем считается личный бюджет индексера. Называют его те, кому нужен круг короче
        #: настоящего, - тесты сроков.
        self.budget_of = budget_of
        #: Индексеры, не уложившиеся в личный бюджет последнего поиска - по именам.
        self.silent: tuple[str, ...] = ()
        #: Индексеры, отдавшие полную страницу последнего поиска, - по именам.
        self.capped: tuple[str, ...] = ()
        #: Индексеры, которых Prowlarr увёл в недоступные, - по именам. Молчунами они не
        #: считаются: молчун не ответил нам, а этих мы и не спрашивали (TC-259).
        self.banned: tuple[str, ...] = ()
        self._roster = IndexerRoster(self._api, spawn=heal)
        self._circle = IndexerCircle(self._api, slack=slack, budget_of=budget_of)
        #: Начало поиска - от него считается остаток цели (:meth:`spare`, TC-228).
        #: Клиент живёт ровно один поиск, поэтому «создан» и «начат» тут одно и то же.
        self._began = time.monotonic()
        #: То же начало, но по стенным часам: с ними сверяются отметки отказов, которые
        #: ставит Prowlarr (TC-291). Монотонные тут не годятся - у них своя точка отсчёта,
        #: общей с чужими отметками у них нет.
        self._begun_at = time.time()
        #: Первый круг ещё не сделан: цель ему не указ - он и есть поиск.
        self._first = True
        #: 🔴 TC-1046. Потолок ПЕРВОГО круга. Цель ему по-прежнему не указ, а вот бюджет
        #: самого медленного опорного - указ: круг ждёт каждого опорного отдельно, и без
        #: потолка ценой меню были двадцать секунд Knaben (TC-226). Отставший при этом не
        #: выброшен, его забирает долив. Опускают эту отметку те, кому нужен круг короче
        #: настоящего, - тесты сроков, ровно как :attr:`budget_of`.
        self.first_cap: float = FIRST_CIRCLE_TIMEOUT
        #: 🔴 TC-386. Пол бюджета ВТОРОГО круга: потолком ему служит остаток цели
        #: (:meth:`spare`), но ниже этой отметки он не опускается. Обычный пол -
        #: :data:`~torrcast.domain.goal_spare.CIRCLE_SHARE`: круг, спрошенный меньше чем на
        #: секунду, - гарантированный молчун. Добор по второму имени картины поднимает пол
        #: до целой цели: без второго имени картина пропадает из каталога, а медленный, но
        #: живой ответ индексера (99-я доля - 5.6 с) в десять секунд укладывается.
        self.cap_floor: float = CIRCLE_SHARE
        #: 🔴 TC-512. Частный бюджет добора за съеденной целью уже выдан. Охраняемых
        #: заходов на пути до трёх, а превышение цели терпится ровно одно: круг с полом в
        #: секунду стоит замеренных 2.0-4.0 с (круг ждёт каждого опорного отдельно), и
        #: раздать его каждому значило бы дать молчуну не сузить каталог, а затормозить путь.
        self.over_goal: bool = False

    @property
    def answered(self) -> set[str]:
        """Кто ответил нам за ЭТОТ поиск - хоть строкой, хоть честным нулём (TC-510).

        Отсюда единственное право на отказ: пока хоть кто-то отвечал, пустота это
        урезанный каталог, а не отсутствие каталога.
        """
        return self._circle.answered

    def spare(self) -> float:
        """Сколько секунд цели этот поиск ещё не потратил (TC-228)."""
        return goal_spare(time.monotonic() - self._began)

    def circle_cap(self) -> float:
        """Потолок бюджета СЛЕДУЮЩЕГО круга: остаток цели, но не ниже :attr:`cap_floor`."""
        return max(self.spare(), self.cap_floor)
