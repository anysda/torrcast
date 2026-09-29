"""Серии сериала в раннем ответе карточки: каталог по первым раздачам, TVmaze не ждут."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

import web.early_seasons
import web.preview
from torrcast.domain.entry import Entry
from torrcast.domain.json_value import JsonValue
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from web.early_seasons import early_seasons
from web.preview import preview
from web.request import Request

_Rows = dict[int, list[JsonValue]]
_EPISODE: JsonValue = {"n": 1, "dur": 0.0, "watched": False, "pos": 0.0}
_PACK = Release(raw_name="Во все тяжкие S01", title="Во все тяжкие", kind="tv", season=1)


class _Catalog:
    """Каталог сериала: помнит, сколько ему позволили ждать молчащий TVmaze."""

    def __init__(self, known: _Rows, pending: bool = False) -> None:
        self.known, self.pending, self.colds = known, pending, list[float]()

    def rows(
        self, picture: Picture, releases: Sequence[Release], saved: _Rows, cold: float
    ) -> tuple[_Rows, bool, list[int]]:
        self.colds.append(cold)
        return self.known, self.pending, []


def _series(*releases: Release) -> Picture:
    return Picture("Во все тяжкие", 2008, "tv", releases=list(releases))


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web.early_seasons, "_seen", {})


def test_the_catalogue_rows_come_with_the_first_releases_without_waiting_tvmaze() -> None:
    catalog = _Catalog({1: [_EPISODE], 2: [_EPISODE]})
    seasons, _layout = early_seasons(_series(_PACK), None, catalog=catalog)
    assert seasons == [{"n": 1, "episodes": [_EPISODE]}, {"n": 2, "episodes": [_EPISODE]}]
    assert catalog.colds == [0.0], "ранний ответ не ждёт TVmaze, только заводит его"


def test_nothing_early_without_releases_a_catalogue_or_a_series() -> None:
    catalog = _Catalog({1: [_EPISODE]})
    film = Picture("Тачки", 2006, "movie", releases=[_PACK])
    assert early_seasons(None, None, catalog=catalog) == ([], [])
    assert early_seasons(_series(), None, catalog=catalog) == ([], [])
    assert early_seasons(film, None, catalog=catalog) == ([], [])
    assert early_seasons(_series(_PACK), None, catalog=_Catalog({})) == ([], [])


def test_a_series_in_the_history_shows_its_rows_by_the_bookmark_before_any_indexer() -> None:
    # The full card plays the bookmark's seasons with the bookmark release, so an empty pool
    # does not keep the list back; a history row with no release to play gives nothing.
    catalog = _Catalog({1: [_EPISODE], 2: [_EPISODE]})
    own = _series()
    saved = Entry(title="Во все тяжкие", magnet="magnet:?xt=urn:btih:" + "a" * 40, season=1)
    saved.episodes = [[1, 1]]
    seasons, _layout = early_seasons(None, saved, own, catalog)
    assert [tab["n"] for tab in seasons if isinstance(tab, dict)] == [1, 2]
    saved.magnet = ""
    web.early_seasons._seen.clear()
    assert early_seasons(None, saved, own, catalog) == ([], [])


def test_a_catalogue_waiting_for_tvmaze_is_asked_again_not_every_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [0.0]
    monkeypatch.setattr(web.early_seasons, "_clock", lambda: now[0])
    catalog = _Catalog({1: [_EPISODE]}, pending=True)
    for tick in (0.0, 0.05, 0.5, 1.2):
        now[0] = tick
        early_seasons(_series(_PACK), None, catalog=catalog)
    assert len(catalog.colds) == 2


def test_the_preview_of_a_series_shows_the_episodes_while_the_circle_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = _Catalog({1: [_EPISODE]})
    monkeypatch.setattr(web.preview, "PATIENCE", 0.0)
    monkeypatch.setattr(web.preview, "early_picture", lambda _query, _key: _series(_PACK))
    monkeypatch.setattr(
        web.preview,
        "early_seasons",
        lambda pool, entry, own: early_seasons(pool, entry, own, catalog),
    )

    class _Warm:
        def ready(self, _query: str) -> None:
            return None

        def ask(self, _screen: Sequence[str]) -> int:
            return 0

    class _Related:
        def of(self, _title: str, _series: bool) -> None:
            return None

        def waiting(self, _title: str, _series: bool) -> bool:
            return False

    query = {"title": "Во все тяжкие", "year": "2008", "kind": "tv"}
    request = Request(method="GET", path="/api/card/tv:bb:2008", query=query, body={})
    answer = preview(request, "tv:bb:2008", _Warm(), _Related())
    assert answer is not None
    body = json.loads(answer.body)
    assert (body["searching"], body["seasons"]) == (True, [{"n": 1, "episodes": [_EPISODE]}])


def test_a_row_of_the_early_answer_plays_only_with_the_release_of_the_card() -> None:
    # The page keeps the contract as text beside the node harness of the play buttons. An early
    # row has no release, and the show picking its own missed "2nd GIG" s2e20 on releases counted
    # through; the press waits for the body that names the release and presses the row there.
    static = Path(__file__).resolve().parents[1] / "web" / "static"
    series = (static / "card-series.js").read_text(encoding="utf-8")
    card = (static / "card.js").read_text(encoding="utf-8")
    shown = card.split("  _show(root, key, query, data) {", 1)[1].split("\n  },", 1)[0]
    played = card.split("  _play(data, key, query, voices, fromStart, season, episode) {", 1)[1]
    assert "const play = () => (data.searching ? TCCardSeries._wait(key, row) : " in series
    assert "TCCard._pressAgain(next, key, data);" in shown
    assert "TCCard._pressed = null;" in played.split("\n  },", 1)[0]
