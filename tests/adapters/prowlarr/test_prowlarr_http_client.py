"""Проверяет HTTP-механику Prowlarr на подставленных ответах."""

from torrcast.adapters.prowlarr.prowlarr_http_client import ProwlarrHttpClient


class _Response:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> object:
        return {"rows": 3}


class _Session:
    def __init__(self) -> None:
        self.timeout = 0.0
        self.posted: tuple[str, object, float] | None = None

    def get(self, url: str, timeout: float) -> _Response:
        self.timeout = timeout
        return _Response()

    def post(self, url: str, json: object, timeout: float) -> None:
        self.posted = (url, json, timeout)


def test_исполняет_запрос_с_переданным_таймаутом() -> None:
    session = _Session()
    payload = ProwlarrHttpClient().get_json(
        session, "http://prowlarr/search", 3.0, "http://prowlarr"
    )
    assert payload == {"rows": 3}
    assert session.timeout == 3.0


def test_лечит_индексер_с_назначенными_правилом_таймаутами() -> None:
    session = _Session()
    ProwlarrHttpClient().probe(
        session,
        "http://prowlarr/indexer/7",
        "http://prowlarr/indexer/test",
        15.0,
        10.0,
        "http://prowlarr",
    )
    assert session.timeout == 15.0
    assert session.posted == (
        "http://prowlarr/indexer/test",
        {"rows": 3},
        10.0,
    )
