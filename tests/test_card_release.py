"""Ключ раздачи карточки берётся из файлов серии прежде дорожек."""

from typing import cast

from torrcast.domain.media import Media
from torrcast.domain.release import Release
from web.card_release import card_release
from web.heard import Heard


def test_episode_files_choose_the_release_key_over_the_track_lookup() -> None:
    episode = Release(raw_name="Show S01", title="Show", magnet="magnet:?xt=urn:btih:" + "a" * 40)
    heard = Heard(media=cast(Media, None), native=False, studios=(), release="b" * 40)

    assert card_release(episode, heard) == "a" * 40


def test_movies_keep_the_track_lookup_release() -> None:
    heard = Heard(media=cast(Media, None), native=False, studios=(), release="b" * 40)

    assert card_release(None, heard) == "b" * 40
