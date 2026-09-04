"""Проверяет второй источник постеров: сверенный id, отказ на тёзках, ужатый адрес."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tests.fakes.json_client import FakeJsonClient
from torrcast.adapters.wiki.imdb_poster import ImdbPoster
from torrcast.adapters.wiki.poster_files import POSTER_WIDTH
from torrcast.domain.facts.ask import Ask

#: Сырой адрес постера в том виде, в каком его называет подсказчик.
RAW = "https://m.media-amazon.com/images/M/MV5BNWI5OTEzMzE@._V1_.jpg"
SMALL = f"https://m.media-amazon.com/images/M/MV5BNWI5OTEzMzE@._V1_UX{POSTER_WIDTH}_.jpg"
PICTURE = b"\xff\xd8\xff\xe0picture"


@dataclass
class FakeBytesClient:
    """Двойник загрузчика: помнит адреса и отдаёт байты."""

    body: bytes = PICTURE
    asked: list[str] = field(default_factory=list)

    def fetch(self, address: str, timeout: float) -> bytes:
        self.asked.append(address)
        return self.body


@dataclass
class FakeCatalogue:
    """Двойник офлайн-карты имён: отвечает заранее известными id."""

    known: dict[tuple[str, int | None], str] = field(default_factory=dict)
    asked: list[tuple[str, int | None, str]] = field(default_factory=list)

    def ids(self, pictures: list[tuple[str, int | None, str]]) -> dict[tuple[str, int | None], str]:
        self.asked.extend(pictures)
        return {
            (title, year): self.known[(title, year)]
            for title, year, _kind in pictures
            if (title, year) in self.known
        }


def _row(one: str, name: str, year: int | None, kind: str, image: str = RAW) -> dict[str, Any]:
    """Строка ответа подсказчика."""
    row: dict[str, Any] = {"id": one, "l": name, "y": year, "qid": kind}
    if image:
        row["i"] = {"imageUrl": image}
    return row


def _imdb(rows: dict[str, list[dict[str, Any]]], catalogue: Any = None) -> Any:
    """Подсказчик, отвечающий на каждое спрошенное имя своим списком."""

    def answer(host: str, path: str, params: dict[str, str]) -> Any:
        asked = path.removeprefix("/suggestion/x/").removesuffix(".json")
        from urllib.parse import unquote

        return {"d": rows.get(unquote(asked), [])}

    client = FakeJsonClient(answer)
    return ImdbPoster(client, FakeBytesClient(), catalogue), client


def test_original_name_named_by_the_source_itself_brings_a_poster() -> None:
    """Оригинальное имя, которым источник зовёт картину сам, - это её постер."""
    imdb, _ = _imdb({"Les parasites": [_row("tt0233258", "Les parasites", 1999, "movie")]})
    ask = Ask("Паразиты", 1999, "movie", "Les parasites")
    assert imdb.wanted([ask], 5.0) == {ask: [SMALL, RAW]}


def test_two_namesakes_of_one_year_leave_the_line_a_line() -> None:
    """Двум тёзкам одного года постер не выдаётся ни одному: чужой хуже пустого.

    🔴 Это и есть «Брат» 2025 года: под именем ``Brat`` в том же году стоят польская
    картина и индийская, обе с обложкой, и ранжировщик ставит первой индийскую.
    """
    imdb, _ = _imdb(
        {
            "Brat": [
                _row("tt35064377", "Brat", 2025, "movie"),
                _row("tt29930430", "Brat", 2025, "movie"),
            ]
        }
    )
    ask = Ask("Брат", 2025, "movie", "Brat")
    assert imdb.wanted([ask], 5.0) == {ask: []}


def test_a_stranger_named_otherwise_is_refused_even_when_it_is_the_only_one() -> None:
    """Единственный подошедший по году и роду - ещё не наша картина.

    🔴 На «Брат» подсказчик отдаёт ``Father Mother Sister Brother`` 2025 года: год и род
    сходятся, имя - нет. Без сверки имени он и приезжал бы человеку в список.
    """
    imdb, _ = _imdb({"Brat": [_row("tt31189315", "Father Mother Sister Brother", 2025, "movie")]})
    ask = Ask("Брат", 2025, "movie", "Brat")
    assert imdb.wanted([ask], 5.0) == {ask: []}


def test_the_offline_map_answers_the_russian_name_without_the_network() -> None:
    """Русское имя сверяет карта на диске, а подсказчик зовётся уже по её id."""
    catalogue = FakeCatalogue({("Решала: Брат", 2022): "tt19412968"})
    imdb, client = _imdb(
        {"tt19412968": [_row("tt19412968", "Reshala: Brat", 2022, "movie")]}, catalogue
    )
    ask = Ask("Решала: Брат", 2022, "movie", "")
    assert imdb.wanted([ask], 5.0) == {ask: [SMALL, RAW]}
    assert [path for _host, path, _params in client.calls] == ["/suggestion/x/tt19412968.json"]


def test_an_id_without_a_picture_falls_back_to_the_original_name() -> None:
    """Карта назвала id, картинки у него нет - остаётся второй путь, по имени."""
    catalogue = FakeCatalogue({("Паразиты", 2016): "tt4688294"})
    imdb, _ = _imdb(
        {
            "tt4688294": [_row("tt4688294", "Parasites", 2016, "movie", image="")],
            "Parasites": [_row("tt4688294", "Parasites", 2016, "movie")],
        },
        catalogue,
    )
    ask = Ask("Паразиты", 2016, "movie", "Parasites")
    assert imdb.wanted([ask], 5.0) == {ask: [SMALL, RAW]}


def test_namesakes_differing_only_in_kind_are_not_asked_of_the_map() -> None:
    """Пара «имя, год», разошедшаяся только родом, у карты не спрашивается вовсе.

    Карта отвечает на пару, а не на тройку: спроси её тут - сериал получил бы id фильма.
    """
    catalogue = FakeCatalogue({("Зона отчуждения. Финал", 2019): "tt9999999"})
    imdb, _ = _imdb({}, catalogue)
    asks = [
        Ask("Зона отчуждения. Финал", 2019, "tv", ""),
        Ask("Зона отчуждения. Финал", 2019, "movie", ""),
    ]
    assert imdb.wanted(asks, 5.0) == {asks[0]: [], asks[1]: []}
    assert catalogue.asked == []


def test_a_year_apart_is_a_different_picture() -> None:
    """Год сверяется ровно: соседний год - это соседняя картина, а не эта."""
    imdb, _ = _imdb({"Parasites": [_row("tt4688294", "Parasites", 2016, "movie")]})
    ask = Ask("Паразиты", 2017, "movie", "Parasites")
    assert imdb.wanted([ask], 5.0) == {ask: []}


def test_a_game_is_not_a_picture() -> None:
    """Игра под именем фильма - не картина, и её обложка сюда не едет."""
    imdb, _ = _imdb(
        {
            "The Matrix: Path of Neo": [
                _row("tt0451118", "The Matrix: Path of Neo", 2005, "videoGame")
            ]
        }
    )
    ask = Ask("Матрица: Путь Нео", 2005, "movie", "The Matrix: Path of Neo")
    assert imdb.wanted([ask], 5.0) == {ask: []}


def test_a_broken_source_says_no_picture_rather_than_raising() -> None:
    """Обрыв второго источника выглядит как «картинки нет», а не как исключение."""

    def answer(host: str, path: str, params: dict[str, str]) -> Any:
        raise OSError("оборвалось")

    imdb = ImdbPoster(FakeJsonClient(answer), FakeBytesClient())
    ask = Ask("Паразиты", 1999, "movie", "Les parasites")
    assert imdb.wanted([ask], 5.0) == {ask: []}


def test_bytes_come_from_the_narrowed_address_first() -> None:
    """Байты берутся с ужатого адреса; сырой остаётся запасным."""
    files = FakeBytesClient()
    client = FakeJsonClient(
        lambda host, path, params: {"d": [_row("tt0233258", "Les parasites", 1999, "movie")]}
    )
    imdb = ImdbPoster(client, files)
    ask = Ask("Паразиты", 1999, "movie", "Les parasites")
    assert imdb.bodies(imdb.wanted([ask], 5.0), 5.0) == {ask: PICTURE}
    assert files.asked == [SMALL]
