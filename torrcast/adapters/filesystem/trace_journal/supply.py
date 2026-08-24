"""Поле снабжения: сколько исходника реально привозит рой."""

from torrcast.adapters.filesystem.trace_journal.emit import emit


def supply(ratio: float, got: float, need: float, enough: bool) -> None:
    emit(
        "play",
        "supply",
        ratio=round(ratio, 2),
        got=round(got, 2),
        need=round(need, 2),
        enough=enough,
    )
