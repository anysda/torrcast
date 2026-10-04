"""Checks that the viewer's text waits the quorum until a row fits the year its query named."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from torrcast.adapters.prowlarr import indexer_circle as indexer_circle_module
from torrcast.adapters.prowlarr.circle_wait import circle_wait
from torrcast.adapters.prowlarr.indexer_circle import IndexerCircle
from torrcast.adapters.prowlarr.spawn_ask import _Ask
from torrcast.domain.query_fits import query_fits
from torrcast.domain.raw_result import RawResult

_FILM_1995 = "Призрак в доспехах / Kokaku kidotai (1995) BDRip 1080p"
_SERIES_2026 = "Призрак в доспехах / Ghost in the Shell (2026) WEB-DL 1080p [S01, 1-10 из 12]"
_HEVC_2026 = "Призрак в доспехах / Ghost in the Shell [S01] (2026) WEBRip-HEVC 1080p"


def _answer(ask: _Ask, after: float, title: str) -> threading.Timer:
    def said() -> None:
        ask.rows = [RawResult(title=title, info_hash="0" * 40, seeders=88)]
        ask.done.set()

    timer = threading.Timer(after, said)
    timer.start()
    return timer


def _waited(asked: list[_Ask], query: str) -> tuple[list[_Ask], float]:
    began = time.monotonic()
    core = circle_wait(
        asked, names=False, began=began, slack=0.0, grace=0.2, fits=query_fits(query)
    )
    return core, time.monotonic() - began


@pytest.mark.machine
def test_rows_of_another_year_leave_the_quorum_waited() -> None:
    """RuTor brought the 1995 film to "... 2026": the series only Knaben brings is waited."""
    knaben, rutor = _Ask("Knaben", 1.5), _Ask("RuTor", 1.5)
    _answer(rutor, 0.1, _FILM_1995)
    _answer(knaben, 0.9, _SERIES_2026)
    core, elapsed = _waited([knaben, rutor], "Призрак в доспехах 2026")
    assert knaben in core and knaben.done.is_set() and not knaben.waived
    assert elapsed >= 0.9, f"let the quorum go at {elapsed:.2f} s with no row of 2026"


@pytest.mark.machine
def test_an_hevc_row_of_the_year_leaves_the_quorum_waited() -> None:
    """RuTor's only 2026 row was HEVC, which the default cannot play: Knaben is waited."""
    knaben, rutor = _Ask("Knaben", 1.5), _Ask("RuTor", 1.5)
    _answer(rutor, 0.1, _HEVC_2026)
    _answer(knaben, 0.9, _SERIES_2026)
    core, elapsed = _waited([knaben, rutor], "Призрак в доспехах 2026")
    assert knaben in core and knaben.done.is_set() and not knaben.waived
    assert elapsed >= 0.9, f"let the quorum go at {elapsed:.2f} s on an HEVC row of 2026"


@pytest.mark.machine
def test_a_row_of_the_year_named_opens_the_grace() -> None:
    """The others brought the year asked: Knaben is not waited past the grace."""
    knaben, rutor = _Ask("Knaben", 5.0), _Ask("RuTor", 5.0)
    _answer(rutor, 0.1, _SERIES_2026)
    late = _answer(knaben, 1.5, _SERIES_2026)
    core, elapsed = _waited([knaben, rutor], "Призрак в доспехах 2026")
    late.cancel()
    assert core == [rutor] and knaben.waived
    assert 0.25 <= elapsed < 0.8, f"waited {elapsed:.2f} s, not the grace past RuTor"


@pytest.mark.machine
def test_a_query_without_a_year_opens_the_grace_on_any_row() -> None:
    knaben, rutor = _Ask("Knaben", 5.0), _Ask("RuTor", 5.0)
    _answer(rutor, 0.1, _FILM_1995)
    late = _answer(knaben, 1.5, _SERIES_2026)
    core, elapsed = _waited([knaben, rutor], "Призрак в доспехах")
    late.cancel()
    assert core == [rutor] and knaben.waived
    assert 0.25 <= elapsed < 0.8, f"waited {elapsed:.2f} s, not the grace past RuTor"


def test_the_circle_waits_by_the_query_it_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(indexer_circle_module, "send_circle", lambda *_a, **_k: ([], []))
    monkeypatch.setattr(indexer_circle_module, "circle_wait", lambda *_a, **k: seen.update(k) or [])
    IndexerCircle(api=None).run([], "Призрак в доспехах 2026", 10)  # type: ignore[arg-type]
    assert not seen["fits"](RawResult(title=_FILM_1995, info_hash="0" * 40))
    assert seen["fits"](RawResult(title=_SERIES_2026, info_hash="0" * 40, seeders=88))
