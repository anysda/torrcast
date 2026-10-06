"""Зеркало :mod:`torrcast.runtime.wire_cli`: команда ``cast`` узнаёт картину по карте."""

from __future__ import annotations

import pytest

import torrcast.usecases.discover._search_state as _search_state
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.runtime import wire_cli
from torrcast.runtime.facts_wiring import FACTS


def test_the_command_line_recognizes_the_picture_by_the_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Без распознавателя круг ``cast`` не спрашивал имена картины: «Dune» не приходил."""
    dune = MapPicture("Дюна", 2021, False, "Dune: Part One", 1000000)
    monkeypatch.setattr(wire_cli, "wire", lambda: None)
    monkeypatch.setattr(
        FACTS.catalogue, "pictures", lambda title: [dune] if title == "Дюна" else []
    )

    wire_cli.wire_cli()

    assert _search_state._search_recognize("Дюна", 0.0) == dune
    assert _search_state._search_recognize("Дюна 1984", 0.0) is None
