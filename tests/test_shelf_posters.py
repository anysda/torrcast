"""Проверяет обложки полки главной: имя только у легших байтов, и видно, что ещё едет."""

from __future__ import annotations

import threading
import time
from collections.abc import Sequence
from pathlib import Path

from hass.hit_posters import FIELD
from hass.shelf_posters import ShelfPosters
from tests.test_hit_posters import POSTER, FakeSource, _hits, _row
from torrcast.domain.facts.ask import Ask
from torrcast.domain.json_value import JsonValue

_SETTLE = 5.0


class _SlowIt(FakeSource):
    """Байты «Оно» стоят за затвором, байты «Тачек» приходят сразу."""

    def bodies(self, wanted: dict[Ask, list[str]], timeout: float) -> dict[Ask, bytes]:
        if any(ask.title == "Оно" for ask in wanted) and self.gate is not None:
            self.gate.wait(_SETTLE)
        return {ask: POSTER for ask, pages in wanted.items() if pages}


def _until(done: object, limit: float = _SETTLE) -> None:
    deadline = time.monotonic() + limit
    while not done() and time.monotonic() < deadline:  # type: ignore[operator]
        threading.Event().wait(0.02)


def test_the_shelf_names_a_cover_as_soon_as_its_bytes_land(tmp_path: Path) -> None:
    """Застрявшая картинка пачки не держит показ уже легшей: полка не ждёт всех байтов."""
    gate = threading.Event()
    hits = _hits(tmp_path, _SlowIt(pages={"Тачки": ["Cars"], "Оно": ["It"]}, gate=gate))
    rows: list[JsonValue] = [_row(), _row("Оно", 2017)]
    try:
        ShelfPosters(hits).ask(rows)
        _until(lambda: FIELD in ShelfPosters(hits).landed(rows)[0])  # type: ignore[operator]
        cars, it = ShelfPosters(hits).landed(rows)
        assert isinstance(cars, dict) and FIELD in cars
        assert isinstance(it, dict) and FIELD not in it, "полка назвала обложку без байтов"
        assert ShelfPosters(hits).arriving(rows)
    finally:
        gate.set()
    _until(lambda: not ShelfPosters(hits).arriving(rows))
    cars, it = ShelfPosters(hits).landed(rows)
    assert isinstance(it, dict) and FIELD in it
    assert not ShelfPosters(hits).arriving(rows)


def test_a_picture_without_a_cover_is_not_arriving(tmp_path: Path) -> None:
    """Картине статьи нет: ждать её нечего, и заход полок не стоит за ней."""
    hits = _hits(tmp_path, FakeSource(pages={}))
    rows: list[JsonValue] = [_row("Нет такой", 1999)]

    ShelfPosters(hits).ask(rows)

    assert not ShelfPosters(hits).arriving(rows)
    assert isinstance(ShelfPosters(hits).landed(rows)[0], dict)
    assert FIELD not in ShelfPosters(hits).landed(rows)[0]  # type: ignore[operator]


def test_arriving_ignores_a_miss_waiting_for_its_retry(tmp_path: Path) -> None:
    """Отложенный повтор - не «в пути»: полка не ждёт картину, спросить которую ещё рано."""
    hits = _hits(tmp_path, FakeSource(pages={"Тачки": ["Cars"]}, body=None))
    rows: Sequence[object] = [_row()]

    ShelfPosters(hits).ask(list(rows))  # type: ignore[arg-type]
    _until(lambda: not hits.arriving(list(rows)))  # type: ignore[arg-type]

    assert hits.pending(list(rows))  # type: ignore[arg-type]
    assert not hits.arriving(list(rows))  # type: ignore[arg-type]
