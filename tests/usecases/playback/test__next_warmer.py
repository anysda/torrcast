"""Зеркало прогрева следующей серии: когда он собирается и чем греет."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from tests.fakes import composition
from tests.fakes.torrent_engine import FakeTorrentEngine
from torrcast.adapters.recode.recode_dir import RECODE_DIR
from torrcast.adapters.recode.recoder import Recoder
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.hls_settings import PLAYING_FLAG
from torrcast.domain.media import Media
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.playback._next_warmer import _next_warmer

_FILES = [
    TorrFile(index=0, name="Erin - 01.mkv", size=700),
    TorrFile(index=1, name="Erin - 02.mkv", size=700),
    TorrFile(index=2, name="Sound/Erin - 01.mka", size=100),
    TorrFile(index=3, name="Sound/Erin - 02.mka", size=100),
]


@pytest.fixture(autouse=True)
def _world(monkeypatch: pytest.MonkeyPatch) -> None:
    """Карта опорных кадров и паспорт - готовые: ни сети, ни ffmpeg тут нет."""
    composition.use_prober(monkeypatch, lambda source, **_: Media(duration=300.0))


def _serial(apart: bool) -> Entry:
    return Entry(
        title="Эрин",
        magnet="magnet:?x",
        kind="tv",
        file_idx=0,
        voiced_apart=apart,
        season=1,
        episode=1,
        episodes=[[1, 1, 0, 700], [1, 2, 1, 700]],
    )


def test_a_film_has_no_next_episode_to_warm_up(tmp_path: Path) -> None:
    """У фильма следующей серии нет и быть не может - греть нечего."""
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    entry = Entry(title="Кино", magnet="magnet:?x")

    assert _next_warmer(config, FakeTorrentEngine(), "hash", entry) is None


def test_the_last_episode_of_the_release_ends_the_chain(tmp_path: Path) -> None:
    """Последняя серия раздачи: цепочка кончилась, а не «греем по кругу»."""
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    entry = _serial(apart=False)
    entry.episode = 2

    engine = FakeTorrentEngine(torrent_files=list(_FILES))

    assert _next_warmer(config, engine, "hash", entry) is None


def test_the_next_episode_is_warmed_from_its_own_video(tmp_path: Path) -> None:
    """Греется файл СЛЕДУЮЩЕЙ серии, а не тот, который играет сейчас."""
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    engine = FakeTorrentEngine(torrent_files=list(_FILES))

    made = _next_warmer(config, engine, "hash", _serial(apart=False))

    assert made is not None
    assert made.source == "http://fake/hash/1"
    assert made.voice == "", "звук внутри видео - второму входу взяться неоткуда"


def test_the_next_episode_keeps_its_track_apart(tmp_path: Path) -> None:
    """Звук отдельным файлом: прогрев следующей серии берёт ЕЁ дорожку, а не текущую."""
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    engine = FakeTorrentEngine(torrent_files=list(_FILES))

    made = _next_warmer(config, engine, "hash", _serial(apart=True))

    assert made is not None
    assert made.voice == "http://fake/hash/3"


def test_the_next_episode_is_assembled_without_touching_the_running_show(tmp_path: Path) -> None:
    """Сборка прогрева следующей серии не трогает каталог ИДУЩЕГО показа.

    Зовут её посреди показа, когда текущая серия легла на диск целиком, и каталог
    сегментов у неё тот же самый - боевой. Прежде она брала его через
    :func:`_state.hls_dir`, то есть ГОТОВИЛА под новый показ: выметала куски, плейлист и
    флажок картинки. Флажок и есть доказательство, по которому CLI отличает картинку от
    упаковки, и жил он после этого доли секунды (TC-884: показ на 350 с бюджета погашен
    своим же ``cast``, зритель увидел это как вылет посреди серии).
    """
    out = tmp_path / "hls"
    out.mkdir()
    (out / PLAYING_FLAG).write_text("")
    (out / "v7.ts").write_text("кусок идущего показа")
    (out / "index.m3u8").write_text("#EXTM3U")
    alive = sorted(item.name for item in out.iterdir() if item.is_file())
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"), hls_dir=str(out))
    engine = FakeTorrentEngine(torrent_files=list(_FILES))

    made = _next_warmer(config, engine, "hash", _serial(apart=False))

    assert made is not None, "греть есть что - иначе проверка не доходит до каталога"
    rival = cast(Recoder, made.rival)
    assert rival is not None and rival.spare == out / RECODE_DIR, (
        "каталог кусков назван от боевого hls_dir - проверке есть чему краснеть"
    )
    assert sorted(item.name for item in out.iterdir() if item.is_file()) == alive


def test_warming_switched_off_leaves_the_next_episode_alone(tmp_path: Path) -> None:
    """Прогрев выключен настройкой - следующая серия его не воскрешает."""
    config = Config(warm=False, warm_dir=str(tmp_path / "warm"))
    engine = FakeTorrentEngine(torrent_files=list(_FILES))

    assert _next_warmer(config, engine, "hash", _serial(apart=True)) is None
