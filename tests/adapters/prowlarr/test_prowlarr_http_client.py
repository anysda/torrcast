"""Проверяет HTTP-механику Prowlarr на подставленных ответах."""

from torrcast.adapters.prowlarr.prowlarr_http_client import ProwlarrHttpClient


class _Response:
    def __init__(self) -> None:
        self.closed = False

    def raise_for_status(self) -> None:
        pass

    def json(self) -> object:
        return {"rows": 3}

    def close(self) -> None:
        self.closed = True


class _Session:
    def __init__(self) -> None:
        self.timeout = 0.0
        self.posted: tuple[str, object, float] | None = None
        self.response = _Response()
        self.post_response = _Response()

    def get(self, url: str, timeout: float) -> _Response:
        self.timeout = timeout
        return self.response

    def post(self, url: str, json: object, timeout: float) -> _Response:
        self.posted = (url, json, timeout)
        return self.post_response


def test_исполняет_запрос_с_переданным_таймаутом() -> None:
    session = _Session()
    payload = ProwlarrHttpClient().get_json(
        session, "http://prowlarr/search", 3.0, "http://prowlarr"
    )
    assert payload == {"rows": 3}
    assert session.timeout == 3.0
    assert session.response.closed


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
    assert session.response.closed and session.post_response.closed
