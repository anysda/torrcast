"""Проверяет контракт прокатных имён по оригиналу."""

from torrcast.ports.ru_names import RuNames


class Catalogue:
    def ru_names(
        self, pictures: list[tuple[str, int | None, str]]
    ) -> dict[tuple[str, int | None], list[str]]:
        return {(title, year): ["Аватар"] for title, year, _kind in pictures}

    def original_ids(
        self, pictures: list[tuple[str, int | None, str]]
    ) -> dict[tuple[str, int | None], list[str]]:
        return {(title, year): ["tt0499549"] for title, year, _kind in pictures}


def test_the_port_carries_original_year_and_type_to_the_catalogue() -> None:
    port: RuNames = Catalogue()

    assert port.ru_names([("Avatar", 2009, "movie")]) == {("Avatar", 2009): ["Аватар"]}
    assert port.original_ids([("Avatar", 2009, "movie")]) == {("Avatar", 2009): ["tt0499549"]}
