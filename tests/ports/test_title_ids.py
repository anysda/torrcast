"""Проверяет контракт точных IMDb-id по прокатным именам."""

from torrcast.ports.title_ids import TitleIds


class Catalogue:
    def ids(self, pictures: list[tuple[str, int | None, str]]) -> dict[tuple[str, int | None], str]:
        return {(title, year): "tt0242653" for title, year, _kind in pictures}


def test_the_port_carries_name_year_and_type_to_the_catalogue() -> None:
    port: TitleIds = Catalogue()

    assert port.ids([("Матрица: Революция", 2003, "movie")]) == {
        ("Матрица: Революция", 2003): "tt0242653"
    }
