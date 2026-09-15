"""Каталог сериалов карточки: id раз на картину, серии с датой выхода, закладка поверх."""

from __future__ import annotations

from collections.abc import Mapping

from torrcast.domain.json_value import JsonValue
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from web.series_catalog import COLD, RETRY, SeriesCatalog

SHOW = Picture(title="Show", year=2020, kind="tv", original="Show")
RELEASE = Release(raw_name="Show S01E01", title="Show", kind="tv", season=1, episode=1)


class _Tvmaze:
    def __init__(self, aired: Mapping[tuple[int, int], tuple[str, str]], pending: bool) -> None:
        self.answer = (aired, pending)
        self.waits: list[float] = []

    def __call__(
        self, _tconst: str, wait: float
    ) -> tuple[Mapping[tuple[int, int], tuple[str, str]], bool]:
        self.waits.append(wait)
        return self.answer


def _catalog(ids: list[str], tvmaze: _Tvmaze) -> SeriesCatalog:
    def series_id(title: str, _original: str, _year: int | None) -> str:
        ids.append(title)
        return "tt0000001" if title == "Show" else ""

    return SeriesCatalog(
        series_id, lambda _t: {1: (1, 2)}, tvmaze, lambda: "2026-09-15T08:00:00+00:00"
    )


def test_every_episode_comes_at_once_and_the_one_to_come_carries_its_date() -> None:
    asked: list[str] = []
    tvmaze = _Tvmaze(
        {(1, 1): ("2020-01-01", "2020-01-01"), (1, 2): ("2026-09-20", "2026-09-20")}, False
    )
    catalog = _catalog(asked, tvmaze)

    rows, pending, layout = catalog.rows(SHOW, [RELEASE], {})
    catalog.rows(SHOW, [RELEASE], {})

    assert (pending, layout) == (False, [])
    assert rows == {
        1: [
            {"n": 1, "dur": 0.0, "watched": False, "pos": 0.0},
            {"n": 2, "dur": 0.0, "watched": False, "pos": 0.0, "air": "2026-09-20"},
        ]
    }
    assert (asked, tvmaze.waits) == (["Show"], [COLD, COLD]), "id ищется раз на картину"


def test_the_bookmark_rows_lie_over_the_catalogue_by_episode_number() -> None:
    catalog = _catalog([], _Tvmaze({}, True))
    watched: list[JsonValue] = [{"n": 1, "dur": 1300.0, "watched": True, "pos": 1300.0}]
    extra: list[JsonValue] = [{"n": 1, "dur": 0.0, "watched": False, "pos": 0.0}]

    rows, pending, _layout = catalog.rows(SHOW, [RELEASE], {1: watched, 3: extra})

    assert pending is True, "TVmaze ещё в пути - карточка переспросит"
    assert rows[1] == [
        watched[0],
        {"n": 2, "dur": 0.0, "watched": False, "pos": 0.0},
    ]
    assert rows[3] == extra


def test_a_series_outside_the_catalogue_has_no_rows() -> None:
    other = Picture(title="Unknown", year=2020, kind="tv")
    assert _catalog([], _Tvmaze({}, True)).rows(other, [RELEASE], {}) == ({}, False, [])


def test_a_series_the_names_did_not_know_is_asked_again_after_a_while() -> None:
    """Индекс имён достраивается после запуска: пустой id не держится до перезапуска."""
    asked: list[str] = []
    known: list[str] = []
    moment = [0.0]

    def series_id(title: str, _original: str, _year: int | None) -> str:
        asked.append(title)
        return known[0] if known else ""

    catalog = SeriesCatalog(
        series_id,
        lambda _t: {1: (1, 2)},
        _Tvmaze({}, False),
        lambda: "2026-09-15T08:00:00+00:00",
        lambda: moment[0],
    )

    assert catalog.rows(SHOW, [RELEASE], {}) == ({}, False, [])
    known.append("tt0000001")
    assert catalog.rows(SHOW, [RELEASE], {}) == ({}, False, []), "до срока не переспрашивает"
    moment[0] = RETRY

    rows, _pending, _layout = catalog.rows(SHOW, [RELEASE], {})

    assert (sorted(rows), len(asked)) == ([1], 2)


def test_a_list_not_numbered_as_the_releases_comes_with_its_season_counts_interns() -> None:
    """IMDb 3 и 2 серии, раздачи зовут сезон 5, TVmaze молчит: список есть, строка сквозная."""
    imdb = {1: (1, 2, 3), 2: (1, 2)}
    fifth = Release(raw_name="Show S05E01", title="Show", kind="tv", season=5, episode=1)
    catalog = SeriesCatalog(
        lambda *_: "tt0000001", lambda _t: imdb, _Tvmaze({}, True), lambda: "2026-09-15"
    )
    saved: list[JsonValue] = [{"n": 1, "dur": 0.0, "watched": False, "pos": 0.0}]

    rows, pending, layout = catalog.rows(SHOW, [fifth], {})

    assert ({s: len(r) for s, r in rows.items()}, pending, layout) == ({1: 3, 2: 2}, True, [3, 2])
    assert catalog.rows(SHOW, [fifth], {5: saved}) == ({}, True, []), "закладка считает раздачей"
    imdb.pop(1)
    assert catalog.rows(SHOW, [fifth], {}) == ({}, True, []), "без первого сезона номера не счесть"
