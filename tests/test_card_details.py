"""Мелкие расчёты полного тела карточки."""

from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.card_details import CardDetails


def test_the_details_count_each_named_indexer_once() -> None:
    releases = [Release(raw_name="one", title="One", indexer="a", indexers=("a", "b"))]

    assert CardDetails.sources_count(releases) == 2


def test_the_details_group_voices_and_mark_the_selected_one() -> None:
    lead = Release(raw_name="One 1080p LostFilm", title="One", quality="1080p", seeders=4)
    picture = Picture(title="One", year=2020, kind="movie", releases=[lead])

    voices = CardDetails.voices(Plan(picture=picture, ranked=[lead], runtime=0, warn_mbit=0))

    assert voices == [{"name": "LostFilm", "quality": "1080p", "seeders": 4, "default": True}]
