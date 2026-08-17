"""Ищет для сценариев раздачи во внешнем каталоге торрентов."""

from typing import Any, Protocol, TypeAlias

#: Строка сырой выдачи индексера (:class:`~torrcast.adapters.prowlarr.raw_result.
#: RawResult`). Полей тут не названо ни одного нарочно: каталог отдаёт строки, а читает
#: их разбор имён - тому, кто просто спросил каталог, о строке известно только что она
#: оттуда приехала.
RawRow: TypeAlias = Any


class TorrentIndex(Protocol):
    def search(self, query: str, limit: int = 100) -> list[RawRow]: ...


class IndexerHttpClient(Protocol):
    def new_session(self) -> Any: ...
    def get_json(self, session: Any, url: str, timeout: float, base_url: str) -> Any: ...
    def post(self, session: Any, url: str, body: Any, timeout: float) -> None: ...
    def probe(
        self,
        session: Any,
        indexer_url: str,
        test_url: str,
        list_timeout: float,
        test_timeout: float,
        base_url: str,
    ) -> None: ...
