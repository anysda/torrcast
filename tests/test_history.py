"""Закладки продукта как список экрана «Продолжить»."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import web.history as history_module
from tests.fakes.state_store import FakeStateStore
from torrcast.domain.entry import Entry
from torrcast.domain.json_value import JsonValue
from torrcast.ports.state_store import slot as state_slot
from web.answer import JSON
from web.history import history
from web.request import Request


@pytest.fixture(autouse=True)
def _posters(monkeypatch: pytest.MonkeyPatch) -> None:
    """История зовёт приговор обложек, но тесты не ходят в сеть."""
    monkeypatch.setattr(
        history_module,
        "hits",
        SimpleNamespace(
            offer=lambda records: [
                {**record, "poster": "abc"} if isinstance(record, dict) else record
                for record in records
            ]
        ),
    )


def _asked() -> dict[str, list[dict[str, JsonValue]]]:
    answer = history(Request("GET", "/api/history", {}, {}))
    assert answer.code == 200
    assert answer.kind == JSON
    body: dict[str, list[dict[str, JsonValue]]] = json.loads(answer.body)
    return body


def test_a_finished_bookmark_does_not_show_up() -> None:
    fake = FakeStateStore()
    state = fake.load()
    state.entries["movie:done:2020"] = Entry(
        "Done", "magnet:done", kind="movie", pos=100.0, dur=100.0, updated="2026-01-01"
    )
    fake.save(state)
    state_slot.install(fake)

    assert _asked()["items"] == []


def test_bookmarks_come_back_freshest_first() -> None:
    fake = FakeStateStore()
    state = fake.load()
    state.entries["movie:old:2019"] = Entry(
        "Old", "magnet:old", kind="movie", pos=10.0, dur=100.0, updated="2026-01-01T00:00:00"
    )
    state.entries["movie:new:2021"] = Entry(
        "New", "magnet:new", kind="movie", pos=20.0, dur=100.0, updated="2026-02-01T00:00:00"
    )
    fake.save(state)
    state_slot.install(fake)

    items = _asked()["items"]
    assert [item["key"] for item in items] == ["movie:new:2021", "movie:old:2019"]


def test_an_item_carries_the_fields_the_tile_needs() -> None:
    fake = FakeStateStore()
    state = fake.load()
    state.entries["tv:show:2022"] = Entry(
        "Show",
        "magnet:show",
        kind="tv",
        pos=30.0,
        dur=1200.0,
        updated="2026-03-01T00:00:00",
        year=2022,
        season=1,
        episode=2,
        query="show season two",
    )
    fake.save(state)
    state_slot.install(fake)

    item = _asked()["items"][0]
    assert item["key"] == "tv:show:2022"
    assert item["title"] == "Show"
    assert item["query"] == "show season two"
    assert item["kind"] == "tv"
    assert item["year"] == 2022
    assert item["label"] == ""
    assert item["pos"] == 30.0
    assert item["dur"] == 1200.0
    assert item["resumable"] is True
    assert isinstance(item["poster"], str) and item["poster"]
    assert item["shown"] == "Show"


def test_the_shown_name_speaks_the_original_under_english(_english: None) -> None:
    """§8: закладка на главной говорит найденной латиницей, а не записью, под английским."""
    fake = FakeStateStore()
    state = fake.load()
    state.entries["movie:matrix:1999"] = Entry(
        "Матрица",
        "magnet:matrix",
        kind="movie",
        pos=10.0,
        dur=100.0,
        updated="2026-01-01T00:00:00",
        original="The Matrix",
    )
    fake.save(state)
    state_slot.install(fake)

    item = _asked()["items"][0]

    assert item["title"] == "Матрица"
    assert item["shown"] == "The Matrix"


def test_the_shown_name_stays_recorded_under_russian_even_with_an_original(
    _russian_product: None,
) -> None:
    """Позитивный контроль: под русским языком найденная латиница ничего не меняет."""
    fake = FakeStateStore()
    state = fake.load()
    state.entries["movie:matrix:1999"] = Entry(
        "Матрица",
        "magnet:matrix",
        kind="movie",
        pos=10.0,
        dur=100.0,
        updated="2026-01-01T00:00:00",
        original="The Matrix",
    )
    fake.save(state)
    state_slot.install(fake)

    item = _asked()["items"][0]

    assert item["title"] == "Матрица"
    assert item["shown"] == "Матрица"


def test_history_keeps_only_tiles_the_poster_verdict_covered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Continue watching проходит тот же приговор, что поиск, и не обещает битую картинку."""
    fake = FakeStateStore()
    state = fake.load()
    for number, title in enumerate(("Есть", "Нет", "Тоже есть"), 1):
        state.entries[f"movie:{title}:2026"] = Entry(
            title,
            f"magnet:{title}",
            kind="movie",
            pos=10.0,
            dur=100.0,
            updated=f"2026-01-0{number}",
        )
    fake.save(state)
    state_slot.install(fake)
    seen: list[dict[str, JsonValue]] = []

    def _offer(records: list[JsonValue]) -> list[JsonValue]:
        seen.extend(record for record in records if isinstance(record, dict))
        return [
            {**record, "poster": "abc"}
            if isinstance(record, dict) and record["title"] != "Нет"
            else record
            for record in records
        ]

    monkeypatch.setattr(history_module, "hits", SimpleNamespace(offer=_offer))

    items = _asked()["items"]

    assert [item["title"] for item in items] == ["Тоже есть", "Есть"]
    assert all(item["poster"] == "abc" for item in items)
    assert [record["original"] for record in seen] == [None, None, None]


def test_history_keeps_the_shelf_when_the_poster_source_is_fully_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Граница: молчащий источник не превращает Continue watching в пустую полку."""
    fake = FakeStateStore()
    state = fake.load()
    state.entries["movie:one:2026"] = Entry(
        "Один", "magnet:one", kind="movie", pos=10.0, dur=100.0, updated="2026-01-01"
    )
    state.entries["movie:two:2026"] = Entry(
        "Два", "magnet:two", kind="movie", pos=10.0, dur=100.0, updated="2026-01-02"
    )
    fake.save(state)
    state_slot.install(fake)
    monkeypatch.setattr(history_module, "hits", SimpleNamespace(offer=lambda records: records))

    items = _asked()["items"]

    assert [item["title"] for item in items] == ["Два", "Один"]
    assert all("poster" not in item for item in items)
