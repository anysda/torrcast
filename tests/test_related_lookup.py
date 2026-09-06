"""RelatedLookup: родня по франшизе в фоне, кэш на процесс, форма - как у плитки полок."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.facts.kin import Kin
from torrcast.domain.json_value import JsonValue
from web.related_lookup import RelatedLookup

_ONE = Kin("Q1", "Гарри Поттер и Тайная комната", 2002)
_TWO = Kin("Q2", "Гарри Поттер и Кубок огня", 2005)


def _sync(job: Callable[[], None]) -> None:
    job()


def _passthrough(records: list[JsonValue]) -> list[JsonValue]:
    return records


def test_the_first_ask_starts_the_background_build_and_answers_none_when_still_slow() -> None:
    """Фон не успевает - вопрос честно висит: ``None``, а не выдуманный список."""
    lookup = RelatedLookup(
        franchise=lambda *_a: [_ONE, _TWO], offer=_passthrough, spawn=lambda _job: None
    )

    related = lookup.of("Гарри Поттер и философский камень", False)

    assert related is None


def test_a_synchronous_build_answers_the_very_same_call_with_tiles_shaped_like_shelves() -> None:
    """Фон синхронный (тест) - плитки родни готовы уже к первому ответу, в форме полки."""
    lookup = RelatedLookup(franchise=lambda *_a: [_ONE, _TWO], offer=_passthrough, spawn=_sync)

    related = lookup.of("Гарри Поттер и философский камень", False)

    assert related is not None
    assert len(related) == 2
    first = related[0]
    assert isinstance(first, dict)
    assert set(first) == {"key", "title", "year", "kind", "quality", "poster", "query"}
    assert first["title"] == "Гарри Поттер и Тайная комната"
    assert first["kind"] == "movie"
    assert first["key"] == "movie:гарри-поттер-и-тайная-комната:2002"


def test_an_empty_franchise_is_a_finished_answer_not_a_pending_one() -> None:
    """Родни у картины нет - это законченный пустой ответ, а не «ещё не готово»."""
    lookup = RelatedLookup(franchise=lambda *_a: [], offer=_passthrough, spawn=_sync)

    related = lookup.of("Картина одна на всю франшизу", False)

    assert related == []


def test_the_cached_tiles_answer_the_next_ask_without_asking_wikidata_again() -> None:
    """Второй вопрос о той же картине не зовёт Wikidata заново - ответ уже в кэше."""
    asked: list[str] = []

    def _franchise(title: str, _series: bool, _timeout: float) -> list[Kin]:
        asked.append(title)
        return [_ONE]

    lookup = RelatedLookup(franchise=_franchise, offer=_passthrough, spawn=_sync)
    lookup.of("Гарри Поттер и философский камень", False)

    lookup.of("Гарри Поттер и философский камень", False)

    assert asked == ["Гарри Поттер и философский камень"]


def test_a_pending_build_is_not_started_twice_for_the_same_title() -> None:
    """Второй вопрос, пока фон ещё бежит, не заводит второй параллельный разбор."""
    spawned: list[Callable[[], None]] = []
    lookup = RelatedLookup(franchise=lambda *_a: [_ONE], offer=_passthrough, spawn=spawned.append)
    lookup.of("Гарри Поттер и философский камень", False)

    lookup.of("Гарри Поттер и философский камень", False)

    assert len(spawned) == 1


def test_the_poster_offer_decorates_tiles_the_same_way_as_the_shelves() -> None:
    """Обложка приходит тем же приговором, что и у полок - розыскное поле после него уходит."""

    def _offer(records: list[JsonValue]) -> list[JsonValue]:
        return [
            {**record, "poster": "abc123"} if isinstance(record, dict) else record
            for record in records
        ]

    lookup = RelatedLookup(franchise=lambda *_a: [_ONE], offer=_offer, spawn=_sync)

    related = lookup.of("Гарри Поттер и философский камень", False)

    assert related is not None
    tile = related[0]
    assert isinstance(tile, dict)
    assert tile["poster"] == "abc123"
    assert "original" not in tile
