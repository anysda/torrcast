"""Проверки того, чья озвучка играет на дорожке."""

from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.domain.studios_in import studios_in
from torrcast.domain.track_studio import track_studio

PACK = studios_in("Dub (The Kitchen Russia) + MVO (Good People)")


def _media(*titles: str | None) -> Media:
    return Media(
        tracks=tuple(AudioTrack(index=i, language="rus", title=t) for i, t in enumerate(titles))
    )


def test_track_title_names_the_studio_itself() -> None:
    studio = track_studio(_media("MVO (LostFilm)", None), 0, PACK)
    assert studio is not None and studio.name == "LostFilm"


def test_silent_tracks_read_the_pack_in_order() -> None:
    first = track_studio(_media(None, None), 0, PACK)
    second = track_studio(_media(None, None), 1, PACK)
    assert first is not None and first.name == "The Kitchen Russia"
    assert second is not None and second.name == "Good People"


def test_counts_do_not_match_so_we_do_not_guess() -> None:
    assert track_studio(_media(None, None, None), 0, PACK) is None
    assert track_studio(_media(None, None), 0, ()) is None
