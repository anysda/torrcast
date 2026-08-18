"""Возит запросы к индексерам: разобранный ответ, отправка тела и проверка индексера."""

from typing import Protocol

from torrcast.ports.json_value import JsonValue
from torrcast.ports.torrent_index.indexer_session import IndexerSession


class IndexerHttpClient(Protocol):
    """Сетевая механика индексеров без политики выбора бюджета."""

    def new_session(self) -> IndexerSession:
        """Открыть сессию на весь поиск: ленивая её сборка внутри потоков - гонка."""

    def get_json(
        self, session: IndexerSession, url: str, timeout: float, base_url: str
    ) -> JsonValue:
        """Ответ ручки разобранным JSON; отказ приходит исключением слоя домена."""

    def post(self, session: IndexerSession, url: str, body: JsonValue, timeout: float) -> None:
        """Отправить в ручку тело запроса; ответа не ждут."""

    def probe(
        self,
        session: IndexerSession,
        indexer_url: str,
        test_url: str,
        list_timeout: float,
        test_timeout: float,
        base_url: str,
    ) -> None:
        """Проверить индексер, поглотив сетевой отказ фонового лечения."""
