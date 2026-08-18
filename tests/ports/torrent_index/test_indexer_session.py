"""Сессия индексеров: договор возит её через границу и читать не разрешает."""

from torrcast.ports.torrent_index import IndexerSession


class _Session:
    """Настоящая сессия: полей у неё сколько угодно, порт о них не знает."""

    def __init__(self) -> None:
        self.headers = {"apikey": "локальный"}


def test_any_session_of_an_adapter_fits_the_contract() -> None:
    """Имя пустое нарочно: сессию заводит адаптер, а порт её только носит."""
    session: IndexerSession = _Session()

    assert isinstance(session, _Session)
