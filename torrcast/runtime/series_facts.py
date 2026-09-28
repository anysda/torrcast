"""Каталог сериала для юнита показа: тот же, что у карточки, но собранный без веба."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from torrcast.ports.series_source import Aired


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class SeriesFacts:
    """Каталог сериала из готовых частей (:mod:`torrcast.runtime.wire_show`) и тестов."""

    ids: Callable[[str, str, int | None], str]
    numbers: Callable[[str], Mapping[int, tuple[int, ...]] | None]
    aired: Callable[[str, float], Aired]
    now: Callable[[], str] = _now
