"""Ищет для сценариев раздачи во внешнем каталоге торрентов."""

from typing import Any, Protocol

from torrcast.domain.release import Release


class TorrentIndex(Protocol):
    def search(self, query: str) -> list[Release]: ...


class IndexerHttpClient(Protocol):
    def new_session(self) -> Any: ...
    def get_json(self, session: Any, url: str, timeout: float, base_url: str) -> Any: ...
    def post(self, session: Any, url: str, body: Any, timeout: float) -> None: ...
