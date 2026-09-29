"""Mirror the held result of the early boundary search."""

from __future__ import annotations

from typing import Any, cast

import pytest

from torrcast.usecases import prepared_next as module
from torrcast.usecases.prepared_next import PreparedNext


def test_the_prepared_search_is_callable() -> None:
    assert callable(PreparedNext)


def _prepared() -> PreparedNext:
    nothing = cast(Any, None)
    return PreparedNext(nothing, "k", nothing, nothing, nothing, (8, 2), nothing, nothing)


def test_a_crashed_search_is_raised_to_the_unit(monkeypatch: pytest.MonkeyPatch) -> None:
    def crash(*_args: object) -> None:
        raise RuntimeError("search crashed")

    monkeypatch.setattr(module, "find_next", crash)
    prepared = _prepared()
    prepared.start()
    with pytest.raises(RuntimeError, match="search crashed"):
        prepared.result()


def test_an_empty_search_still_ends_the_series(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "find_next", lambda *_args: None)
    assert _prepared().result() is None
