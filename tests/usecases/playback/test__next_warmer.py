"""Зеркало прогрева следующей серии: когда он собирается и чем греет."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakes import composition
from tests.fakes.torrent_engine import FakeTorrentEngine
from tests.usecases.playback.world import film_keys
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
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
    composition.use_film_keys(monkeypatch, lambda source: film_keys())
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


def test_warming_switched_off_leaves_the_next_episode_alone(tmp_path: Path) -> None:
    """Прогрев выключен настройкой - следующая серия его не воскрешает."""
    config = Config(warm=False, warm_dir=str(tmp_path / "warm"))
    engine = FakeTorrentEngine(torrent_files=list(_FILES))

    assert _next_warmer(config, engine, "hash", _serial(apart=True)) is None
