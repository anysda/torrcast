"""Фоновая рука прогрева: срочная карточка, поднятая с диска, обновляется из сети следом."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from tests.test_warm_cache import _PLAN, _TOLD, _Circle, _restarted, _sync
from torrcast.usecases.discover.told_circle import ToldCircle


def test_a_card_opened_on_a_circle_from_disk_refreshes_it_in_the_background(
    tmp_path: Path,
) -> None:
    """🔴 Карточка будила круг с диска фоном, и живого круга за ним не шло: пул стоял старым."""
    circle = _Circle(answer=ToldCircle([_PLAN], _TOLD))
    _restarted(tmp_path, circle, _sync)[0].take("Interstellar")
    held: list[Callable[[], None]] = []
    cache, replayed = _restarted(tmp_path, circle, held.append)

    cache.hint("Interstellar")
    while held:
        held.pop(0)()

    assert (replayed, circle.asked) == (["Interstellar"], ["Interstellar", "Interstellar"])
    assert cache.take_live("Interstellar") == [_PLAN]
    assert circle.asked == ["Interstellar", "Interstellar"], "обновление и есть круг показа"
