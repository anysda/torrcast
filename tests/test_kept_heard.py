"""Дорожки закладки по её записи: ответ или честное «не знаю»."""

from __future__ import annotations

from typing import Any

from tests.usecases.rank.releases import media, track
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.infra_error import InfraError
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.kept_heard import kept_heard

_HASH = "b" * 40
_OTHER = Release(raw_name="Film 2010 720p", title="Film", magnet="magnet:?xt=urn:btih:" + "c" * 40)
_PLAN = Plan(
    picture=Picture(title="Film", year=2010, kind="movie", releases=[_OTHER]),
    ranked=[_OTHER],
    runtime=0,
    warn_mbit=0,
)
_MEDIA = media(tracks=(track(0, "rus", "MVO"), track(1, "eng", "Original")))
_LIVE = Entry(title="Film", magnet="magnet:?xt=urn:btih:" + _HASH, dur=7200.0, pos=180.0)


def test_the_tracks_of_the_bookmark_record_answer_for_its_release() -> None:
    read: list[Entry] = []

    def media_of(_config: Config, entry: Entry) -> Any:
        read.append(entry)
        return _MEDIA

    heard, failed = kept_heard(media_of, _PLAN, Config(), _HASH, _LIVE)

    assert failed is False and read == [_LIVE]
    assert heard is not None and heard.release == _HASH and heard.media is _MEDIA


def test_a_silent_bookmark_swarm_is_unknown_not_an_empty_menu() -> None:
    def silent(_config: Config, _entry: Entry) -> Any:
        raise InfraError("no peers")

    assert kept_heard(silent, _PLAN, Config(), _HASH, _LIVE) == (None, True)
