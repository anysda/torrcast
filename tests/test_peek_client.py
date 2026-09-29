"""Checks the records a search client holds before its circle is over."""

from __future__ import annotations

from typing import Any, cast

from hass.peek_client import peek_client
from tests.test_search_progress import _PreviewClient
from tests.test_searching import _CARS
from tests.usecases.discover.world import Indexer, wire_catalogue
from torrcast.usecases.discover.named_round import NamedRound


def _titles(records: list[Any]) -> list[str]:
    return [record["title"] for record in records]


def test_the_rows_in_hand_make_the_records() -> None:
    wire_catalogue()
    records = peek_client("тачки", _PreviewClient(raw=_CARS))
    assert "Тачки 2" in _titles(records)
    assert not any(record["default"] for record in cast("list[dict[str, Any]]", records))


def test_a_round_shows_the_viewers_text_and_the_names_together() -> None:
    wire_catalogue()
    round_ = NamedRound(_PreviewClient(raw=_CARS[:1]))
    round_._named.append(_PreviewClient(raw=_CARS[1:2]))
    assert {"Тачки", "Тачки 2"} <= set(_titles(peek_client("тачки", round_)))


def test_nothing_in_hand_is_no_records() -> None:
    assert peek_client("тачки", Indexer()) == []
    assert peek_client("тачки", None) == []
