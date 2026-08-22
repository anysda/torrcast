"""Зеркало записи показа: паспорт ffprobe уезжает в состояние целиком, а не наполовину."""

from __future__ import annotations

from typing import Any, cast

from tests.usecases.cast_command.world import plan, release
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.cast_command._entry_for import _entry_for
from torrcast.usecases.select._prep import _Prep


def _media() -> Media:
    return Media(
        duration=7200.0,
        tracks=(AudioTrack(index=0, language="rus", title="Дубляж"),),
        video="hevc",
        height=2160,
        video_bps=21.0 * 1e6,
        pix_fmt="yuv420p10le",
        color_trc="smpte2084",
    )


def _entry() -> Any:
    video = TorrFile(index=7, name="кино/film.mkv", size=(30 * 1024**3))
    prep = _Prep(number=1, release=release())
    prep.video, prep.files, prep.media = video, [video], _media()
    return _entry_for(
        cast(Any, plan()), prep, release(), video, _media(), 0, "Дубляж", Args(query=["кино"])
    )


def test_the_passport_reaches_the_record_whole() -> None:
    """Кодек, глубина, кадр и HDR - по ним показ решает, играть копией или перекодом."""
    entry = _entry()

    assert (entry.codec, entry.depth, entry.frame, entry.hdr) == ("hevc", 10, 2160, True)
    assert entry.vbps == 21.0, "вес видеодорожки едет числом, а не набирается вслепую"
    assert not entry.vbps_estimated


def test_the_chosen_file_and_track_reach_the_record() -> None:
    """Юнит играет ТОТ файл и ТУ дорожку, которые выбрал отбор, а не первые попавшиеся."""
    entry = _entry()

    assert (entry.file_idx, entry.audio, entry.voice) == (7, 0, "Дубляж")


def test_missing_video_weight_is_estimated_from_the_chosen_file() -> None:
    """Молчание паспорта не оставляет ровный профиль без целей."""
    video = TorrFile(index=7, name="кино/film.mkv", size=30_000_000_000)
    pack = release("Кино / Movie WEB-DL 1080p")
    prep = _Prep(number=1, release=pack)
    prep.video, prep.files, prep.media = video, [video], _media()
    silent = Media(duration=6000.0, video="h264", height=1080, width=1920)

    entry = _entry_for(cast(Any, plan()), prep, pack, video, silent, 0, "rus", Args(query=["кино"]))

    assert entry.vbps == 40.0, "оценка по выбранному файлу поднимает ровный профиль"
    assert entry.vbps_estimated


def test_a_movie_carries_no_episode_at_all() -> None:
    """У фильма серии нет: ни сезона, ни номера, ни таблицы серий."""
    entry = _entry()

    assert (entry.season, entry.episode, entry.episodes) == (None, None, [])
    assert entry.kind == "movie"


def test_the_query_is_remembered_by_its_slug() -> None:
    """Запись ищется по канону запроса, а не по тому, как его набрали в этот раз."""
    assert _entry().query == "кино"


def test_the_studio_that_played_reaches_the_record() -> None:
    """Сезонная раздача кончится вместе с сезоном, и студия - всё, что от неё останется."""
    video = TorrFile(index=0, name="кино/s01e01.mkv", size=(8 * 1024**3))
    pack = release("Кино / Movie (Сезон 1) WEB-DL 1080p, Dub (The Kitchen Russia)")
    prep = _Prep(number=1, release=pack)
    prep.video, prep.files, prep.media = video, [video], _media()
    silent = Media(duration=7200.0, tracks=(AudioTrack(index=0, language="rus"),))
    entry = _entry_for(cast(Any, plan()), prep, pack, video, silent, 0, "rus", Args(query=["кино"]))

    assert entry.studio == "The Kitchen Russia", "подпись «rus» о студии не говорит ничего"
