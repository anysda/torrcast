"""Фоновая рука прогрева: срочная карточка, поднятая с диска, обновляется из сети следом."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

import web.warm_pump
from tests.test_warm_cache import _PLAN, _TOLD, _cache, _Circle, _restarted, _sync
from torrcast.usecases.discover.told_circle import ToldCircle
from torrcast.usecases.select.plan import Plan


def test_a_card_opened_on_a_circle_from_disk_refreshes_it_in_the_background(
    tmp_path: Path,
) -> None:
    """🔴 Карточка будила круг с диска фоном, и живого круга за ним не шло: пул стоял старым."""
    circle = _Circle(answer=ToldCircle([_PLAN], _TOLD, whole=True))
    _restarted(tmp_path, circle, _sync)[0].take("Interstellar")
    held: list[Callable[[], None]] = []
    cache, replayed = _restarted(tmp_path, circle, held.append)

    cache.hint("Interstellar")
    while held:
        held.pop(0)()

    assert (replayed, circle.asked) == (["Interstellar"], ["Interstellar", "Interstellar"])
    assert cache.take_live("Interstellar") == [_PLAN]
    assert circle.asked == ["Interstellar", "Interstellar"], "обновление и есть круг показа"


def test_a_background_circle_lets_a_show_start_go_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 A shelf circle read its releases from the swarm while a show waited for its own."""
    order: list[str] = []
    monkeypatch.setattr(web.warm_pump, "start_first", lambda: order.append("start first"))
    circle = _Circle()

    def counted(query: str) -> list[Plan]:
        order.append(f"circle {query}")
        return circle(query)

    cache = _cache(counted)

    cache.ask(["Interstellar", "Inception"])

    assert order == [
        "start first",
        "circle Interstellar",
        "start first",
        "circle Inception",
        "start first",
    ]
