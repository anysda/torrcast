"""Каталог раздач за Prowlarr: спрашивает индексеры врозь и сводит их выдачи."""

from __future__ import annotations

from torrcast.adapters.prowlarr.circle_trace import circle_trace
from torrcast.adapters.prowlarr.from_json import from_json
from torrcast.adapters.prowlarr.merge import merge
from torrcast.adapters.prowlarr.prowlarr_http_client import _IndexersUnavailableError
from torrcast.adapters.prowlarr.prowlarr_state import _State
from torrcast.adapters.prowlarr.search_url import search_url
from torrcast.domain.anime_fallback import anime_fallback
from torrcast.domain.capped_indexers import capped_indexers
from torrcast.domain.circle_indexers import circle_indexers
from torrcast.domain.infra_error import InfraError
from torrcast.domain.nothing_found import nothing_found
from torrcast.domain.raw_result import RawResult


class Prowlarr(_State):
    """Каталог раздач за Prowlarr: круг по индексерам врозь и сведённая их выдача.

    Поля одного поиска - личные бюджеты, счёт молчунов и остаток цели - живут в
    :mod:`torrcast.adapters.prowlarr.prowlarr_state`; здесь сам поиск и ничего кроме.
    """

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
