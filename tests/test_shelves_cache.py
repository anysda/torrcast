"""Проверяет ShelvesCache: полки строятся фоном, читаются мгновенно, сеть - не в GET."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from torrcast.adapters.prowlarr.torrent_catalogue import torrent_catalogue
from torrcast.domain.facts.origin import Origin
from torrcast.domain.feed_row import FeedRow
from torrcast.domain.infra_error import InfraError
from torrcast.domain.json_value import JsonValue
from torrcast.domain.raw_result import RawResult
from web.shelves_cache import Feed, Offer, PassportOf, ShelvesCache, Spawn

_MOMENT = datetime(2026, 9, 6, tzinfo=UTC)


def _rows() -> list[FeedRow]:
    return [
        FeedRow(
            RawResult("Матрица 1999 1080p", "a" * 40, 1000, 5, "rutor"),
            datetime(2026, 9, 5, tzinfo=UTC),
        )
    ]


def _many_rows(count: int) -> list[FeedRow]:
    """Лента из count разных картин одной раздачей на каждую - полные и пустые полки."""
    return [
        FeedRow(
            RawResult(f"Картина {index:02d} 2001 1080p", f"{index:040x}", 1000, 5, "rutor"),
            datetime(2026, 9, 5, tzinfo=UTC),
        )
        for index in range(count)
    ]


def _still(_seconds: float) -> None:
    """Сон-пустышка: добор проверяет свои заходы, а не течение времени."""


def _cache(
    tmp_path: Path,
    *,
    feed: Feed | None = None,
    offer: Offer | None = None,
    passport: PassportOf | None = None,
    spawn: Spawn | None = None,
    attempts: int = 1,
    sleep: Callable[[float], None] = _still,
) -> ShelvesCache:
    return ShelvesCache(
        feed=feed or (lambda limit: _rows()),
        catalogue=torrent_catalogue,
        offer=offer or (lambda records: records),
        path=tmp_path / "shelves.json",
        attempts=attempts,
        sleep=sleep,
        passport=passport or (lambda title, series, timeout: Origin()),
        spawn=spawn or (lambda job: None),
        clock=lambda: _MOMENT,
    )


def _tile(shelf: JsonValue, index: int) -> dict[str, JsonValue]:
    """Плитка полки с проверенным типом - тесты читают её поля без гаданий mypy."""
    assert isinstance(shelf, list)
    tile = shelf[index]
    assert isinstance(tile, dict)
    return tile


def test_before_the_first_build_the_shelves_are_empty_not_blocking(tmp_path: Path) -> None:
    """Фон ещё не бегал и диска нет - полки честно пусты, а не выдуманы."""
    body = _cache(tmp_path).get()

    assert body == {"fresh": [], "popular": [], "built_at": None}


def test_rebuild_fills_both_shelves_with_projected_tiles(tmp_path: Path) -> None:
    """После сборки плитка несёт ровно контрактные поля ``/api/shelves``, и ни одного лишнего."""
    cache = _cache(tmp_path)

    cache._rebuild()

    body = cache._body
    assert body is not None
    assert body["built_at"] == "2026-09-06T00:00:00+00:00"
    fresh = body["fresh"]
    assert isinstance(fresh, list)
    assert len(fresh) == 1
    tile = _tile(fresh, 0)
    assert set(tile) == {"key", "title", "shown", "year", "kind", "quality", "poster", "query"}
    assert tile["title"] == "Матрица"
    assert tile["shown"] == "Матрица"


def _offer_with_original(records: list[JsonValue]) -> list[JsonValue]:
    """Подмена ``offer``: как поле пришло бы с найденной латиницей у картины."""
    decorated: list[JsonValue] = []
    for record in records:
        assert isinstance(record, dict)
        decorated.append({**record, "original": "The Matrix"})
    return decorated


def test_a_tile_speaks_the_latin_name_under_english_and_stays_recorded_under_russian(
    tmp_path: Path, _english: None
) -> None:
    """§8: под английским языком плитка говорит найденной латиницей, а не записью."""
    cache = _cache(tmp_path, offer=_offer_with_original)

    cache._rebuild()

    body = cache._body
    assert body is not None
    tile = _tile(body["fresh"], 0)
    assert tile["title"] == "Матрица"
    assert tile["shown"] == "The Matrix"


def test_a_tile_keeps_the_recorded_name_under_russian_even_with_a_latin_original(
    tmp_path: Path, _russian_product: None
) -> None:
    """Позитивный контроль: под русским языком найденная латиница ничего не меняет."""
    cache = _cache(tmp_path, offer=_offer_with_original)

    cache._rebuild()

    body = cache._body
    assert body is not None
    tile = _tile(body["fresh"], 0)
    assert tile["title"] == "Матрица"
    assert tile["shown"] == "Матрица"


def test_a_tile_without_its_own_latin_name_asks_the_passport_under_english(
    tmp_path: Path, _english: None
) -> None:
    """Раздача латиницы не назвала - паспорт добирает её тем же приёмом, что и родня."""
    asked: list[str] = []

    def _passport(title: str, _series: bool, _timeout: float) -> Origin:
        asked.append(title)
        return Origin(title="The Matrix")

    cache = _cache(tmp_path, passport=_passport)

    cache._rebuild()

    body = cache._body
    assert body is not None
    tile = _tile(body["fresh"], 0)
    assert tile["title"] == "Матрица"
    assert tile["shown"] == "The Matrix"
    # Полки собираются раздельно (:meth:`ShelvesCache._rebuild`), и картина, попавшая
    # сразу в обе, спрашивает паспорт дважды - он дисковый кэш, а не сетевой поход.
    assert asked == ["Матрица", "Матрица"]


def test_a_tile_without_its_own_latin_name_never_asks_the_passport_under_russian(
    tmp_path: Path, _russian_product: None
) -> None:
    """Позитивный контроль: под русским языком паспорт не звонит вовсе - незачем."""
    asked: list[str] = []

    def _passport(title: str, _series: bool, _timeout: float) -> Origin:
        asked.append(title)
        return Origin(title="The Matrix")

    cache = _cache(tmp_path, passport=_passport)

    cache._rebuild()

    body = cache._body
    assert body is not None
    tile = _tile(body["fresh"], 0)
    assert tile["title"] == "Матрица"
    assert tile["shown"] == "Матрица"
    assert asked == []


def test_rebuild_persists_the_cache_and_a_fresh_instance_reads_it_back(tmp_path: Path) -> None:
    """Кэш переживает рестарт службы: новый предмет находит собранное на диске."""
    path = tmp_path / "shelves.json"
    built = ShelvesCache(
        feed=lambda limit: _rows(),
        catalogue=torrent_catalogue,
        offer=lambda records: records,
        path=path,
        spawn=lambda job: None,
        clock=lambda: _MOMENT,
    )
    built._rebuild()

    assert path.exists()
    reread = ShelvesCache(
        feed=lambda limit: [],
        catalogue=torrent_catalogue,
        offer=lambda records: records,
        path=path,
        spawn=lambda job: None,
    )

    assert _tile(reread.get()["fresh"], 0)["title"] == "Матрица"


def test_offer_is_the_only_place_a_poster_field_can_come_from(tmp_path: Path) -> None:
    """Обложку дописывает переданный ``offer``, как у выдачи поиска - своего пути тут нет."""
    seen: list[list[JsonValue]] = []

    def fake_offer(records: list[JsonValue]) -> list[JsonValue]:
        seen.append(records)
        return [{**r, "poster": "abc"} if isinstance(r, dict) else r for r in records]

    cache = _cache(tmp_path, offer=fake_offer)

    cache._rebuild()

    body = cache._body
    assert body is not None
    assert _tile(body["fresh"], 0)["poster"] == "abc"
    assert seen, "offer обязан был увидеть плитки перед сборкой ответа"


def test_a_broken_feed_does_not_crash_the_rebuild(tmp_path: Path) -> None:
    """Отказ ленты (Prowlarr лёг) не роняет фон - просто не обновляет полки в этот раз."""

    def failing_feed(limit: int) -> list[FeedRow]:
        raise InfraError("прибили")

    cache = _cache(tmp_path, feed=failing_feed)

    cache._rebuild()  # не должно бросить наружу

    assert cache._body is None


def test_get_starts_the_background_loop_exactly_once(tmp_path: Path) -> None:
    """Фон встаёт при первом обращении и только при нём - не при каждом запросе."""
    calls: list[object] = []
    cache = _cache(tmp_path, spawn=lambda job: calls.append(job))

    cache.get()
    cache.get()
    cache.get()

    assert len(calls) == 1


def test_the_loop_rebuilds_then_sleeps_for_the_configured_period(tmp_path: Path) -> None:
    """Цикл фона: сборка, потом сон на ``every`` секунд, и так по кругу."""
    build_count = 0

    def counting_feed(limit: int) -> list[FeedRow]:
        nonlocal build_count
        build_count += 1
        return []

    slept: list[float] = []

    def stopping_sleep(seconds: float) -> None:
        slept.append(seconds)
        raise RuntimeError("stop the loop for the test")

    cache = ShelvesCache(
        feed=counting_feed,
        catalogue=torrent_catalogue,
        offer=lambda records: records,
        path=tmp_path / "shelves.json",
        attempts=1,
        spawn=lambda job: None,
        sleep=stopping_sleep,
        every=3600.0,
    )

    with pytest.raises(RuntimeError, match="stop the loop"):
        cache._loop()

    assert build_count == 1
    assert slept == [3600.0]


def test_a_short_build_is_topped_up_until_the_shelves_meet_the_floor(tmp_path: Path) -> None:
    """ТЗ §9: короче 20 плиток полка человеку не отдаётся - фон спрашивает ленту ещё."""
    answers = [_many_rows(18), _many_rows(25)]
    calls = 0

    def feed(_limit: int) -> list[FeedRow]:
        nonlocal calls
        answer = answers[min(calls, len(answers) - 1)]
        calls += 1
        return answer

    slept: list[float] = []
    cache = _cache(tmp_path, feed=feed, attempts=3, sleep=slept.append)

    cache._rebuild()

    assert calls == 2
    assert slept == [cache.retry_pause]
    body = cache._body
    assert body is not None
    assert isinstance(body["fresh"], list) and len(body["fresh"]) == 25
    assert isinstance(body["popular"], list) and len(body["popular"]) == 25


def test_a_failed_attempt_is_retried_inside_the_same_rebuild(tmp_path: Path) -> None:
    """Первый заход ленты упал - сборка спрашивает ещё, не дожидаясь следующего часа."""
    calls = 0

    def feed(_limit: int) -> list[FeedRow]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise InfraError("прибили")
        return _many_rows(25)

    cache = _cache(tmp_path, feed=feed, attempts=2)

    cache._rebuild()

    assert calls == 2
    body = cache._body
    assert body is not None
    assert isinstance(body["fresh"], list) and len(body["fresh"]) == 25


def test_a_full_shelf_is_not_replaced_by_a_short_build(tmp_path: Path) -> None:
    """Полная полка остаётся на месте, когда свежая сборка планку не взяла."""
    answers = iter([_many_rows(25), _many_rows(18)])
    cache = _cache(tmp_path, feed=lambda limit: next(answers))

    cache._rebuild()
    cache._rebuild()

    body = cache._body
    assert body is not None
    assert isinstance(body["fresh"], list) and len(body["fresh"]) == 25


def test_all_short_attempts_publish_their_fullest_build(tmp_path: Path) -> None:
    """Источники молчат весь добор - отдаётся самая полная из попыток, честно короткая."""
    answers = iter([_many_rows(10), _many_rows(15)])
    cache = _cache(tmp_path, feed=lambda limit: next(answers), attempts=2)

    cache._rebuild()

    body = cache._body
    assert body is not None
    assert isinstance(body["fresh"], list) and len(body["fresh"]) == 15


def _half_posters(records: list[JsonValue]) -> list[JsonValue]:
    """``offer``-подделка: обложку получают записи с нечётным номером картины в имени."""
    out: list[JsonValue] = []
    for record in records:
        assert isinstance(record, dict)
        number = int(str(record["title"]).split()[1])
        out.append({**record, "poster": "abc"} if number % 2 else record)
    return out


def test_a_picture_without_a_poster_is_replaced_by_the_next_covered_one(
    tmp_path: Path,
) -> None:
    """Полка не несёт заглушек и не короче планки: выброшенное добрано следующими."""
    cache = _cache(tmp_path, feed=lambda limit: _many_rows(60), offer=_half_posters)

    cache._rebuild()

    body = cache._body
    assert body is not None
    for key in ("fresh", "popular"):
        shelf = body[key]
        assert isinstance(shelf, list)
        assert len(shelf) == 30, f"полка {key} стала короче: {len(shelf)}"
        assert all(isinstance(tile, dict) and tile.get("poster") for tile in shelf), (
            f"полка {key} несёт плитку без обложки"
        )
