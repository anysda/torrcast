"""Прогрев следующей серии и её показ приходят к одной полке - при любом приёмнике."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from tests.fakes import composition
from tests.fakes.torrent_engine import FakeTorrentEngine
from torrcast.adapters.stream_pack.hls_dir import hls_dir
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.media import Media
from torrcast.domain.position import Position
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.episode_duration import _duration
from torrcast.usecases.playback._next_warmer import _next_warmer
from torrcast.usecases.playback._tract import _tract
from torrcast.usecases.playback.entry_layout import entry_layout

#: Приёмники, между которыми гуляет профиль вкладки: осторожный и осторожный с потолком
#: куска в 500 КБ - другая сетка при том же контейнере.
_PROFILES: tuple[Profile, ...] = (
    CAUTIOUS,
    replace(CAUTIOUS, key="tight", max_segment_bytes=500_000),
)
_FILES = [
    TorrFile(0, "Futurama - 01.mkv", 180_000_000),
    TorrFile(1, "Futurama - 02.mkv", 91_000_000),
]


class _Screen:
    """Приёмник сборки тракта: ни о чём его не спрашивают."""

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        return None

    def stop(self, quit_app: bool = False) -> None:
        return None

    def position(self, front: float = 0.0) -> Position:
        raise AssertionError("сборка тракта приёмник о месте не спрашивает")


def _serial() -> Entry:
    """Играет s1e1: её паспорт в записи ЧУЖОЙ для s1e2 - тяжёлый H.264 в HDR."""
    return Entry(
        title="Футурама", magnet="magnet:?x", kind="tv", file_idx=0, season=1, episode=1,
        episodes=[[1, 1, 0, 180_000_000], [1, 2, 1, 91_000_000]],
        dur=1400.0, vbps=12.0, codec="h264", depth=8, frame=1080, hdr=True,
    )  # fmt: skip


def _keys(tmp_path: Path, codec: str, profile: Profile) -> tuple[str, str]:
    """Ключ полки прогрева следующей серии и ключ полки её же показа."""
    config = Config(
        recode=True, warm=True, warm_dir=str(tmp_path / "warm"),
        hls_dir=str(tmp_path / "hls"), hls_port=0,
    )  # fmt: skip
    engine = FakeTorrentEngine(torrent_files=list(_FILES))
    warm = _next_warmer(config, engine, "hash", _serial(), profile)
    # Показ той же серии - боевым путём: запись дочитывает паспорт (_duration), раскладка
    # идёт по записи (_play), тракт собирает прогрев показа (_tract).
    source = engine.stream_url("hash", 1)
    shown = _duration("k", _serial().advance(), source)
    grid, whole = entry_layout(config, source, shown, profile, 91_000_000)
    _recoder, show, _feed, server, _screen = _tract(
        config, source, 0, "s1e2", hls_dir(str(tmp_path / "hls")), grid, whole, 0.0,
        max(0.0, shown.vbps), False, _Screen(), profile=profile,
        video_mbit_estimated=shown.vbps_estimated, codec=shown.codec, depth=shown.depth,
    )  # fmt: skip
    server.stop()
    assert warm is not None and show is not None
    return warm.vault.key, show.vault.key


@pytest.mark.parametrize("profile", _PROFILES, ids=lambda item: item.key)
@pytest.mark.parametrize("codec", ["hevc", "h264"])
def test_the_next_episode_warms_onto_the_shelf_its_show_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, codec: str, profile: Profile
) -> None:
    """HEVC в mkv без веса в паспорте (Футурама): вес у показа - оценка по размеру файла.

    Прогрев, считавший вес голым ffprobe, клал сплошной перекод на 8.3 Мбит/с, а показ шёл
    на 3.0: полки разошлись, первый кусок следующей серии паковался на лету.
    """
    passport = Media(duration=1352.9, tracks=(), video=codec, height=720, width=960)
    composition.use_prober(monkeypatch, lambda source, **_: passport)

    warm, show = _keys(tmp_path, codec, profile)

    assert warm == show


@pytest.mark.parametrize("codec", ["hevc", "h264"])
def test_a_new_receiver_profile_moves_the_warm_shelf_with_the_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, codec: str
) -> None:
    """Сменился профиль приёмника - сменилась и нарезка прогрева, без правки прогрева."""
    passport = Media(duration=1352.9, tracks=(), video=codec, height=720, width=960)
    composition.use_prober(monkeypatch, lambda source, **_: passport)

    shelves = [_keys(tmp_path / item.key, codec, item) for item in _PROFILES]

    assert all(warm == show for warm, show in shelves)
    assert len({warm for warm, _show in shelves}) == len(_PROFILES), shelves
