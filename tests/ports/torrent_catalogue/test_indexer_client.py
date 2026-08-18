"""Клиент индексеров: договор его возит и ручек звать не разрешает."""

from torrcast.ports.torrent_catalogue import IndexerClient


class _Prowlarr:
    """Настоящий клиент: ручек у него сколько угодно, порт о них не знает."""

    def __init__(self) -> None:
        self.budget = 8.0

    def search(self, query: str) -> list[str]:
        return [query]


def test_the_real_client_of_an_adapter_fits_the_carrier() -> None:
    """Имя пустое нарочно: бюджет и счёт молчунов - дело клиента, а не сценария добора."""
    carried: IndexerClient = _Prowlarr()

    assert isinstance(carried, _Prowlarr)
