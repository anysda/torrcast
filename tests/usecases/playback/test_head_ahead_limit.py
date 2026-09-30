"""Голова карточки у вкладки: режется пределом приёмника, а не целью сетки."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from tests.usecases.playback.test_head_ahead import _ENTRY, _heads, _now
from torrcast.domain.config import Config
from torrcast.usecases.playback.head_ahead import HeadAhead

#: Цель сетки и предел приёмника - разные числа, как у вкладки: голова обязана взять предел.
_TAB: Any = SimpleNamespace(max_segment_bytes=28_000_000, segment_limit=80_000_000)


def test_the_head_is_cut_to_the_receivers_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Голова карточки режется тем же пределом, что показ, а не целью сетки."""
    _heads(monkeypatch, "k")
    caps: list[object] = []

    def lay(*args: object, **_kw: object) -> bool:
        caps.append(args[7])
        return True

    HeadAhead(spawn=_now, lay=lay).want(Config(), _TAB, object(), _ENTRY)  # type: ignore[arg-type]

    assert caps == [80_000_000]
