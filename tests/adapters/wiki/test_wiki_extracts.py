"""Проверяет выделенную единицу пакетного запроса статей."""

from tests.articles import wiki_reply
from tests.fakes.json_client import FakeJsonClient
from torrcast.adapters.wiki.wiki_extracts import _LANES, wiki_extracts


def test_the_wave_keeps_the_measurement_that_bought_parallel_batches() -> None:
    reason = wiki_extracts.__doc__ or ""

    assert "503 картины" in reason and "49%" in reason and "14%" in reason
    assert "один пакет 0.78 с, три очередью 2.14 с, три разом 0.83 с" in reason
    assert "не успели спросить" in reason and "статьи нет" in reason


def test_the_wave_names_the_picture_whose_whole_request_answered() -> None:
    key = ("Тачки", 2006)

    candidates, _payload, answered, complete = wiki_extracts(
        FakeJsonClient(lambda host, path, params: wiki_reply()), [key], 1.0
    )

    assert candidates[key][0] == "Тачки"
    assert answered == {key}
    assert complete == {key}, "a complete wave can settle an unfit namesake later"


def test_the_cartoon_series_qualifier_reaches_wikipedia_from_a_crowded_menu() -> None:
    """Уточнение мультсериала доезжает до Википедии с настоящего меню, а не только в списке.

    Потолок волны один на ВСЁ меню, и место в очереди меряется им. Сериал стоит тут
    последним из четырнадцати картин - в самом невыгодном месте раздачи мест по глубине
    (TC-844): именно так и было в меню, где у «Войн клонов» не печаталось ни строки.
    """
    clones: tuple[str, int | None] = ("Звёздные войны: Войны клонов", 2008)
    menu: list[tuple[str, int | None]] = [(f"Картина {n}", 2000 + n) for n in range(13)]
    menu.append(clones)
    kinds = dict.fromkeys(menu, "movie") | {clones: "tv"}
    client = FakeJsonClient(lambda host, path, params: wiki_reply())

    wiki_extracts(client, menu, 1.0, kinds)

    asked = {name for _host, _path, params in client.calls for name in params["titles"].split("|")}
    assert "Звёздные войны: Войны клонов (мультсериал, 2008)" in asked


def test_every_candidate_reaches_the_last_home_tile() -> None:
    """The home warmup can confirm an absence rather than guessing after five names."""
    odyssey = ("Одиссея", 2026)
    wanted: list[tuple[str, int | None]] = [(f"Картина {n}", 2000 + n) for n in range(13)]
    wanted.append(odyssey)
    client = FakeJsonClient(lambda _host, _path, _params: {"query": {"pages": []}})

    wiki_extracts(client, wanted, 1.0, dict.fromkeys(wanted, "movie"))

    asked = {name for _host, _path, params in client.calls for name in params["titles"].split("|")}
    assert "Одиссея (фильм, 2026)" in asked
    assert "одиссея" in asked
    assert len(client.calls) > _LANES, "home needs a second five-lane source interval"


def test_a_card_wave_marks_its_source_requests_foreground() -> None:
    """Клик несёт свой класс до единственного общего HTTP-диспетчера."""
    client = FakeJsonClient(lambda _host, _path, _params: {"query": {"pages": []}})

    wiki_extracts(client, [("Тачки", 2006)], 1.0, foreground=True)

    assert client.foregrounds == [True]
