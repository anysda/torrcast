"""Отдаёт тестам выдачу индексеров из подложенного каталога и помнит все запросы."""

from __future__ import annotations

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.raw_result import RawResult


class FakeProwlarr:
    """Индексер, который русский запрос знает хуже латинского - как живой.

    Подаётся сценарию поиска параметром ``indexer``: сам он и фабрика клиента, и
    клиент, поэтому вызов ``(url, apikey)`` возвращает его же.
    """

    def __init__(self, catalog: dict[str, list[RawResult]]) -> None:
        self.catalog = catalog
        self.asked: list[str] = []
        #: Пол бюджета круга и признак выданного за целью бюджета - оба из договора
        #: клиента (:class:`~torrcast.ports.torrent_catalogue.indexer_client.IndexerClient`): добор
        #: двигает первый и читает второй, и молчаливой подделки у них не бывает.
        self.cap_floor = 1.0
        self.over_goal = False
        #: Счёт выпавших и опоздавших - часть договора клиента
        #: (:class:`~torrcast.ports.torrent_catalogue.indexer_client.IndexerClient`):
        #: круг говорит человеку и о том, чего в выдаче нет. Тут не выпал никто.
        self.silent: tuple[str, ...] = ()
        self.banned: tuple[str, ...] = ()
        self.reported_silent: set[str] = set()

    def __call__(self, url: str, apikey: str) -> FakeProwlarr:
        return self

    def search(self, query: str, limit: int = 100) -> list[RawResult]:
        self.asked.append(query)
        found = self.catalog.get(query.casefold(), [])
        if not found:
            raise NotFoundError(f"по запросу «{query}» ничего не нашлось")
        return found

    def late(self) -> list[RawResult]:
        """Опоздавших нет: круг тут отвечает разом (TC-118)."""
        return []

    def waiting(self) -> tuple[str, ...]:
        """В пути никого: круг тут отвечает разом (TC-703)."""
        return ()

    def spare(self) -> float:
        """Остаток цели: тут поиск мгновенный, поэтому цела вся (TC-228)."""
        from torrcast.domain.goal_spare import GOAL

        return GOAL
