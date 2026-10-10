"""Файл отбора карточки: в раздаче закладки - её файл, а не первая серия плана."""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.select.plan import Plan
from web.bookmark_args import bookmark_args
from web.bookmark_picker import bookmark_picker

_HASH = "b" * 40
_MAGNET = "magnet:?xt=urn:btih:" + _HASH
_SHOW = Release(raw_name="Show S01-S05 720p", title="Show", magnet=_MAGNET)
_EPISODES = [
    TorrFile(1, "Show_s01/Show.S01E01.720p.mkv", 1 << 30),
    TorrFile(2, "Show_s01/Show.S01E02.720p.mkv", 1 << 30),
    TorrFile(88, "Show_s05/Show.S05E01.720p.mkv", 1 << 30),
]


def _series_plan() -> Plan:
    picture = Picture(title="Show", year=2004, kind="tv", releases=[_SHOW])
    return Plan(picture=picture, ranked=[_SHOW], runtime=0, warn_mbit=0)


def _kept(magnet: str, file_idx: int) -> Entry:
    return Entry(title="Show", magnet=magnet, kind="tv", file_idx=file_idx, season=5, episode=1)


def test_the_card_warms_the_bookmark_file_not_the_first_episode_of_its_plan() -> None:
    """План карточки целит в s1e1, а «Играть» продолжит s5e1: греть надо файл закладки."""
    args = bookmark_args(_series_plan(), "show", _HASH, "s5e1")

    chosen = bookmark_picker(args, _kept(_MAGNET, 88))(_series_plan(), _SHOW, _EPISODES)

    assert chosen.index == 88


def test_a_release_other_than_the_bookmark_keeps_the_usual_choice() -> None:
    """Номер файла закладки живёт только в её раздаче: в чужой он значит другой файл."""
    other = Release(
        raw_name="Show S01 1080p", title="Show", magnet="magnet:?xt=urn:btih:" + "c" * 40
    )
    args = bookmark_args(_series_plan(), "show", "", "")

    chosen = bookmark_picker(args, _kept(_MAGNET, 88))(_series_plan(), other, _EPISODES)

    assert chosen.index == 1, "без закладки в этой раздаче - первая серия плана"


def test_no_bookmark_keeps_the_usual_choice() -> None:
    args = bookmark_args(_series_plan(), "show", "", "")

    assert bookmark_picker(args, None)(_series_plan(), _SHOW, _EPISODES).index == 1
