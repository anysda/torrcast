"""Каталог раздач за Prowlarr: спрашивает индексеры врозь и сводит их выдачи."""

from __future__ import annotations

import time
from collections.abc import Callable

from torrcast.adapters.prowlarr.circle_trace import circle_trace
from torrcast.adapters.prowlarr.from_json import from_json
from torrcast.adapters.prowlarr.indexer_circle import ASK_SLACK, IndexerCircle
from torrcast.adapters.prowlarr.indexer_roster import IndexerRoster
from torrcast.adapters.prowlarr.merge import merge
from torrcast.adapters.prowlarr.prowlarr_api import TIMEOUT, ProwlarrApi
from torrcast.adapters.prowlarr.prowlarr_http_client import _IndexersUnavailableError
from torrcast.adapters.prowlarr.search_url import search_url
from torrcast.domain.anime_fallback import anime_fallback
from torrcast.domain.capped_indexers import capped_indexers
from torrcast.domain.circle_indexers import circle_indexers
from torrcast.domain.goal_spare import CIRCLE_SHARE, goal_spare
from torrcast.domain.indexer_budget import indexer_budget
from torrcast.domain.infra_error import InfraError
from torrcast.domain.nothing_found import nothing_found
from torrcast.domain.raw_result import RawResult


class Prowlarr:
    """Клиент на один поиск: свои бюджеты, свой счёт молчунов, свой остаток цели."""

    def __init__(
        self,
        base_url: str,
        apikey: str,
        timeout: float = TIMEOUT,
        *,
        slack: float = ASK_SLACK,
        budget_of: Callable[[str], float] = indexer_budget,
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
        #: Уже названные человеку выпавшие источники - и молчуны, и заблокированные:
        #: повторный добор не должен повторять строку.
        self.reported_silent: set[str] = set()
        #: Индексеры, которых Prowlarr увёл в недоступные, - по именам. Молчунами они не
        #: считаются: молчун не ответил нам, а этих мы и не спрашивали (TC-259).
        self.banned: tuple[str, ...] = ()
        self._roster = IndexerRoster(self._api)
        self._circle = IndexerCircle(self._api, slack=slack, budget_of=budget_of)
        #: Начало поиска - от него считается остаток цели (:meth:`spare`, TC-228).
        #: Клиент живёт ровно один поиск, поэтому «создан» и «начат» тут одно и то же.
        self._began = time.monotonic()
        #: То же начало, но по стенным часам: с ними сверяются отметки отказов, которые
        #: ставит Prowlarr (TC-291). Монотонные тут не годятся - у них своя точка отсчёта,
        #: общей с чужими отметками у них нет.
        self._begun_at = time.time()
        #: Первый круг ещё не сделан: он один и идёт без оглядки на цель.
        self._first = True
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

    def search(self, query: str, limit: int = 100) -> list[RawResult]:
        """Найти раздачи во всех подключённых индексерах: :class:`InfraError` - Prowlarr
        недоступен или ответил не тем, :class:`~torrcast.domain.not_found_error.
        NotFoundError` - пригодных раздач нет.

        Спрашиваем КАЖДЫЙ индексер отдельным запросом (:meth:`_apart`). Список индексеров
        не отдали - остаётся прежний общий запрос, один на всех.
        """
        found = self._apart(query, limit)
        general = self._url(query, limit)
        results = found if found is not None else from_json(self._api.get_json(general))
        if not results:
            raise nothing_found(
                query, self.banned, self._roster.refused(self.banned, self._begun_at), self.silent
            )
        return results

    def late(self, wait: float = 0.0) -> list[RawResult]:
        """Выдача опоздавших: круг ушёл по опорным, а эти доехали уже потом (TC-118)."""
        return self._circle.late(wait)

    def spare(self) -> float:
        """Сколько секунд цели этот поиск ещё не потратил (TC-228)."""
        return goal_spare(time.monotonic() - self._began)

    def circle_cap(self) -> float:
        """Потолок бюджета СЛЕДУЮЩЕГО круга: остаток цели, но не ниже :attr:`cap_floor`."""
        return max(self.spare(), self.cap_floor)

    def _apart(self, query: str, limit: int) -> list[RawResult] | None:
        """Круг по индексерам, где у каждого свой бюджет; ``None`` - список не отдали.

        🔴 Зачем врозь, если у Prowlarr есть общий запрос. Он отвечает, только когда
        опрошены ВСЕ индексеры, и вернуть половину выдачи не умеет. Один залипший
        индексер поэтому стоил не своей задержки, а всего поиска: замерено на живом
        стенде - три индексера ответили за 0.1-0.6 с, четвёртый молчал, и `cast` отдал
        меню через 100.1 с (внутри Prowlarr это ``Failed to read complete http response``
        ровно на сотой секунде - потолок его собственного HTTP-клиента). Второй круг по
        латинскому названию удваивал цену: человек ждал две минуты на живой франшизе.
        Врозь молчун стоит только своего бюджета, а находки остальных приезжают за их
        обычные 0.1-0.6 с.

        Параллель тут не «побольше потоков», а ровно та же, что была: общий запрос
        Prowlarr сам опрашивает индексеры разом. На хост по-прежнему приходится один
        запрос за круг - это важно для тех трекеров, что рассыпаются от нескольких
        одновременных.

        Выдачи склеиваются по ``infoHash``: один и тот же торрент из двух индексеров -
        одна раздача, а не две. Общий запрос отдавал такие строки дважды (на живом стенде
        «матрица»: 190 строк против 179 склеенных).
        """
        known = self._roster.known()
        if not known:
            return None
        self._api.open()  # сессия поднимается ДО потоков: ленивая сборка внутри них - гонка
        known, self.banned = self._roster.usable(known)
        first, later = circle_indexers(known, query)
        # 🔴 TC-228: первый круг идёт в свои личные бюджеты, а каждый следующий - в остаток
        # цели (:meth:`spare`), но не ниже пола (:attr:`cap_floor`). Первый круг это и есть
        # поиск, резать его нечем; а вот второй заход раньше платил хвост первого плюс
        # свой полный - и удваивал цену.
        cap = 0.0 if self._first else self.circle_cap()
        self._first = False
        self._circle.begin()
        got, why_lost = self._circle.run(first, query, limit, cap)
        fallback = bool(later) and anime_fallback(len(merge(*got)), bool(got))
        if fallback:
            # Фолбэк - тоже второй круг, и цель он тратит наравне с добором.
            more, err = self._circle.run(later, query, limit, self.circle_cap())
            got += more
            why_lost = why_lost or err
        self.silent = tuple(self._circle.lost)
        self.capped = capped_indexers(self._circle.counts)
        # 🔴 TC-318. Пул ПУСТ, а опоздавший ещё в пути - вот тут его и дожидаются:
        # показывать всё равно нечего, и он единственный, кто ещё может привезти картину.
        # Пустая выдача ответившего идёт тут наравне с молчанием - строк не приехало ни
        # одной. Замер 11-08-2026 (корпус 170): пул выходил пустым у 23 запросов, ожидание
        # стоило им по 2.1 с, и у двух из них опоздавший вёз ту самую картину, которой не
        # хватало, опаздывая на 0.2 с. Ждём остаток цели: секунды тут покупают не скорость
        # показа, а выбор между «ничего не нашлось» и картиной.
        waiting = self._circle.waiting()
        if not any(got) and (rows := self.late(wait=self.spare())):
            got.append(rows)
        circle_trace(
            got=self._circle.counts,
            silent=self.silent,
            banned=self.banned,
            ms=self._circle.spent,
            fallback=fallback,
            late=waiting,
            budgets={name: self.budget_of(name) for name in self.silent},
        )
        if not got and self.answered:
            # 🔴 TC-510. Круг пуст, но в этом поиске нам уже отвечали: значит молчит не
            # инфраструктура, а вот этот круг - добор второй строкой, фолбэк, переспрос
            # раскладки. Такой круг не вправе отменять поиск: отказ инфры не ловит
            # сценарий добора, и вместе с кругом он выбрасывает уже собранный пул. Замер
            # офлайн: у 4 запросов из 10 (молчит один Knaben) так пропадало готовое меню.
            return []
        if not got:  # молчат все до одного - это не «ничего не нашлось», а инфра
            if self.silent and isinstance(why_lost, _IndexersUnavailableError):
                raise InfraError(f"индексеры не отвечают: {', '.join(self.silent)}")
            raise InfraError(str(why_lost or ""))
        return merge(*got)

    def _url(self, query: str, limit: int, indexer: int | None = None) -> str:
        return search_url(self.base_url, self.apikey, query, limit, indexer)


__all__ = ["Prowlarr"]
