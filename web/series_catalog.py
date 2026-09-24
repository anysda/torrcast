"""Сезоны и серии сериала из каталога, без TorrServer: карточка знает их до первого показа.

IMDb-id сериала даёт карта прокатных имён, номера серий - дисковый индекс IMDb, эфирную
нумерацию и даты выхода - TVmaze с кэшем на диске; какую раскладку показать, решает
:func:`torrcast.domain.series_layout.series_layout` по именам раздач пула. Холодный
TVmaze ждётся не дольше :data:`COLD`: дальше карточка отдаёт то, что есть, и переспрашивает.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from time import monotonic
from typing import Final

from torrcast.adapters.wiki.imdb_episode_index.seasons import seasons
from torrcast.adapters.wiki.tvmaze_episodes import TvmazeEpisodes
from torrcast.domain.facts.settings import EPISODES_PATH
from torrcast.domain.json_value import JsonValue
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.series_layout import series_layout
from torrcast.runtime.facts_wiring import FACTS

#: Сколько первый вопрос сериала ждёт TVmaze: живой отвечает за 0.2-0.5 с (живой приёмник),
#: а весь ответ карточки обещан за 2 с.
COLD: Final = 0.8
#: Сериал без id переспрашивается не раньше этого: индекс имён мог достроиться после однострока.
RETRY: Final = 60.0
#: Строки серий по сезонам, как их отдаёт карточка.
Rows = dict[int, list[JsonValue]]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class SeriesCatalog:
    """Раскладка сериала по картине пула; найденный id сериала ищется раз на процесс."""

    ids: Callable[[str, str, int | None], str]
    numbers: Callable[[str], Mapping[int, tuple[int, ...]] | None]
    aired: Callable[[str, float], tuple[Mapping[tuple[int, int], tuple[str, str]], bool]]
    now: Callable[[], str] = _now
    clock: Callable[[], float] = monotonic
    _ids: dict[str, tuple[str, float]] = field(default_factory=dict)

    def rows(
        self, picture: Picture, releases: Sequence[Release], saved: Rows
    ) -> tuple[Rows, bool, list[int]]:
        """Серии по сезонам, «TVmaze ещё в пути» и числа серий списка чужой раздачам нумерации.

        Ещё не вышедшая серия несёт дату выхода ``air``: страница рисует её серой. Строки
        закладки ``saved`` ложатся поверх по номеру серии: серий каталога они не прячут.
        Список не как у раздач («Интерны» IMDb 60, 60, 61, 98) отдаётся с числами серий
        сезонов: строку показ ищет сквозным номером. Закладка считает серии раздачей, и
        такому списку с ней не сойтись: тогда пусто, как вне каталога.
        """
        key, moment = picture.key, self.clock()
        tconst, asked = self._ids.get(key, ("", float("-inf")))
        if not tconst and moment - asked >= RETRY:
            tconst = self.ids(picture.title, picture.original or "", picture.year)
            self._ids[key] = (tconst, moment)
        if not tconst:
            return {}, False, []  # outside the catalogue the card keeps the release tables
        aired, pending = self.aired(tconst, COLD)
        imdb = self.numbers(tconst) or {}
        layout, direct = series_layout(imdb, aired, releases, saved, self.now())
        if not direct:
            counts = _counts(layout) if not saved else []
            rows = {season: [_row(n, air) for n, air in layout[season]] for season in layout}
            return (rows, pending, counts) if counts else ({}, pending, [])
        out: Rows = {}
        for season in sorted({*layout, *saved}):
            by_number = {n: _row(n, air) for n, air in layout.get(season, ())}
            by_number.update((_number(row), row) for row in saved.get(season, ()))
            out[season] = [by_number[n] for n in sorted(by_number)]
        return out, pending, []


def _counts(layout: Mapping[int, list[tuple[int, str]]]) -> list[int]:
    """Числа серий сезонов 1..N, если каждый сезон считает серии с первой подряд; иначе пусто."""
    counts = [len(layout.get(season, ())) for season in range(1, len(layout) + 1)]
    whole = all(
        [n for n, _air in layout.get(season, ())] == list(range(1, count + 1))
        for season, count in enumerate(counts, 1)
    )
    return counts if counts and whole and all(counts) else []


def _number(row: JsonValue) -> int:
    number = row.get("n") if isinstance(row, dict) else None
    return number if isinstance(number, int) else 0


def _row(number: int, air: str) -> JsonValue:
    row: dict[str, JsonValue] = {"n": number, "dur": 0.0, "watched": False, "pos": 0.0}
    if air:
        row["air"] = air
    return row


#: Каталог боевого пути: карта имён справки, индекс серий IMDb и TVmaze рядом с состоянием.
SERIES: Final = SeriesCatalog(
    FACTS.catalogue.series_id, partial(seasons, EPISODES_PATH), TvmazeEpisodes().aired
)


__all__ = ["SERIES", "SeriesCatalog"]
