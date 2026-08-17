"""Проверяет прогрев куска файла через рой: что просят, сколько берут и когда бросают."""

from __future__ import annotations

from typing import Any, Literal

import pytest

from tests.conftest import module_of
from torrcast.adapters.stream_pack.warm_at import warm_at
from torrcast.domain.warm_open import HEAD_WARM

module = module_of("torrcast.adapters.stream_pack.warm_at")


class _Body:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    def __enter__(self) -> _Body:
        return self

    def __exit__(self, *_: object) -> Literal[False]:
        return False

    def read(self, _size: int) -> bytes:
        return self._chunks.pop(0) if self._chunks else b""


def _swarm(monkeypatch: pytest.MonkeyPatch, chunks: list[bytes]) -> list[Any]:
    seen: list[Any] = []

    def urlopen(request: Any, timeout: float = 0.0) -> _Body:
        seen.append(request)
        return _Body(chunks)

    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    return seen


def test_exactly_the_asked_window_is_pulled_through_the_swarm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Лишнего трафика тут нет: ровно эти байты показ прочитает следующим действием."""
    seen = _swarm(monkeypatch, [b"x" * 1000, b"y" * 24])
    taken = warm_at("http://торрент/поток", 500, 1024)

    assert taken == 1024, "прогрето не то, что взято"
    assert seen[0].headers["Range"] == "bytes=500-1523"


def test_the_default_window_is_the_agreed_head(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _swarm(monkeypatch, [b""])
    warm_at("http://торрент/поток", 0)
    assert seen[0].headers["Range"] == f"bytes=0-{HEAD_WARM - 1}"


def test_a_release_the_show_gave_up_on_is_dropped_mid_pull(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Дотягивать релиз, от которого показ отказался, нельзя: он отъедает полосу у
    выбранного. Проверка живости стоит на каждом куске, а не на входе.
    """
    _swarm(monkeypatch, [b"z" * (1 << 20)] * 8)
    life = iter([True, False, False, False])
    taken = warm_at("http://торрент/поток", 0, 8 << 20, alive=lambda: next(life))
    assert taken == 2 << 20, "прогрев не бросил отвергнутый релиз"
