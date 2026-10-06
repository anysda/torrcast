"""Аргументы отбора карточки: раздача закладки названа, когда она есть в выдаче."""

from __future__ import annotations

from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.bookmark_args import bookmark_args

_HASH = "b" * 40
_OTHER = Release(raw_name="Film 2010 720p", title="Film", magnet="magnet:?xt=urn:btih:" + "c" * 40)
_KEPT = Release(raw_name="Film 2010 1080p", title="Film", magnet="magnet:?xt=urn:btih:" + _HASH)
_PICTURE = Picture(title="Film", year=2010, kind="movie", releases=[_OTHER, _KEPT])


def _plan(*ranked: Release) -> Plan:
    return Plan(picture=_PICTURE, ranked=list(ranked), runtime=0, warn_mbit=0)


def test_a_bookmark_release_in_the_listing_is_named_by_number_and_hash() -> None:
    args = bookmark_args(_plan(_OTHER, _KEPT), "film", _HASH, "")

    assert (args.release, args.release_hash, args.card_release) == (2, _HASH, "")


def test_a_bookmark_release_gone_from_the_listing_is_only_preferred_by_name() -> None:
    args = bookmark_args(_plan(_OTHER), "film", _HASH, "")

    assert (args.release, args.release_hash, args.card_release) == (None, "", _HASH)
