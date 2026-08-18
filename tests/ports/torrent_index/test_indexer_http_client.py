"""Сетевая механика индексеров: сессию порт возит, но не читает."""

from torrcast.ports.json_value import JsonValue
from torrcast.ports.torrent_index import IndexerHttpClient, IndexerSession


class _Session:
    """Сессия, у которой снаружи звать нечего: ровно так её и видит порт."""


class _Client:
    def __init__(self) -> None:
        self.carried: list[IndexerSession] = []

    def new_session(self) -> IndexerSession:
        return _Session()

    def get_json(
        self, session: IndexerSession, url: str, timeout: float, base_url: str
    ) -> JsonValue:
        self.carried.append(session)
        return {"результат": [{"title": "Моана 2"}]}

    def post(self, session: IndexerSession, url: str, body: JsonValue, timeout: float) -> None:
        self.carried.append(session)

    def probe(
        self,
        session: IndexerSession,
        indexer_url: str,
        test_url: str,
        list_timeout: float,
        test_timeout: float,
        base_url: str,
    ) -> None:
        self.carried.append(session)


def test_one_session_is_carried_through_every_call() -> None:
    """Сессия открывается один раз и дальше только ездит из вызова в вызов."""
    spy = _Client()
    client: IndexerHttpClient = spy
    session = client.new_session()

    answer = client.get_json(session, "http://индексер/api", 1.0, "http://индексер")
    client.post(session, "http://индексер/test", answer, 1.0)
    client.probe(session, "http://индексер/api", "http://индексер/test", 1.0, 1.0, "http://и")

    assert isinstance(answer, dict)
    assert spy.carried == [session, session, session], "порт возит ОДНУ сессию, а не заводит свои"
