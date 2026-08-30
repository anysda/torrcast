"""Сеанс показа переводит запись состояния в снимок и разводит уборку по звеньям."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from torrcast.adapters.unit_playback_session import UnitPlaybackSession
from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.domain.torrcast_error import TorrcastError

HASH = "4f2c1a90bd9e3f1fbaa1a8b8b7c0d1e2f3a4b5c6"


@dataclass
class _Entry:
    title: str = "Моана 2"
    magnet: str = f"magnet:?xt=urn:btih:{HASH.upper()}"
    pos: float = 660.0
    dur: float = 5978.0
    label: str = "s1e2"
    quality: str = "1080p"
    dark: float = 0.0
    dark_why: str = ""
    warm: float = 0.0
    file_idx: int = 2
    audio: int = 1
    torrent: str = HASH
    vbps: float = 10.0
    vbps_estimated: bool = False
    done: bool = False
    year: int = 0


@dataclass
class _State:
    entries: dict[str, _Entry] = field(default_factory=dict)
    newest: tuple[str, _Entry] | None = None

    def get(self, key: str) -> _Entry | None:
        return self.entries.get(key)

    def latest(self) -> tuple[str, _Entry] | None:
        return self.newest


@dataclass
class _Wiring:
    config: Any = "конфиг"
    state: _State = field(default_factory=_State)
    released: list[list[str]] = field(default_factory=list)
    reserved: list[Any] = field(default_factory=list)
    address: str = "http://10.0.0.7:8080"
    receiver: str = "chromecast"
    fails: bool = False

    def session(self) -> UnitPlaybackSession:
        return UnitPlaybackSession(
            configuration=lambda: self,
            state=lambda: self.state,
            active=lambda: True,
            unit_key=lambda: "movie:моана-2",
            stop_unit=lambda: None,
            release_torrents=self._release,
            cache_reserve=self._reserve,
            stream_address=self._address,
        )

    def _release(self, config: Any, hashes: Any) -> list[str]:
        self.released.append(list(hashes))
        return list(hashes)

    def _reserve(self, config: Any, entry: Any) -> str:
        self.reserved.append(entry)
        return "в кэше службы запас ещё на 7 мин показа"

    def _address(self, config: Any) -> str:
        if self.fails:
            raise TorrcastError("адреса нет")
        return self.address


def test_the_named_key_wins_over_the_freshest_record() -> None:
    wiring = _Wiring()
    wiring.state.entries["движется"] = _Entry()
    wiring.state.newest = ("свежая", _Entry(title="Другое"))

    shown = wiring.session().snapshot("движется")

    assert shown == PlaybackSnapshot(
        key="движется",
        title="Моана 2",
        position=660.0,
        duration=5978.0,
        label="s1e2",
        quality="1080p",
        file_index=2,
        audio_index=1,
        torrent_hash=HASH,
    )


def test_without_a_key_the_freshest_record_answers() -> None:
    wiring = _Wiring()
    wiring.state.newest = ("свежая", _Entry(title="Другое"))

    shown = wiring.session().snapshot("")

    assert shown is not None and (shown.key, shown.title) == ("свежая", "Другое")


def test_an_empty_state_has_nothing_to_show() -> None:
    assert _Wiring().session().snapshot("") is None


def test_the_reserve_is_asked_about_the_very_record_the_snapshot_came_from() -> None:
    wiring = _Wiring()
    entry = _Entry()
    wiring.state.entries["движется"] = entry
    session = wiring.session()

    shown = session.snapshot("движется")

    assert shown is not None
    assert session.cache_reserve(shown) == "в кэше службы запас ещё на 7 мин показа"
    assert wiring.reserved == [entry]


def test_an_unknown_snapshot_is_not_asked_about_at_all() -> None:
    wiring = _Wiring()

    assert wiring.session().cache_reserve(PlaybackSnapshot("чужая", "Кино")) == ""
    assert wiring.reserved == []


def test_cleanup_never_fails_the_stop() -> None:
    wiring = _Wiring()

    def angry(config: Any, hashes: Any) -> list[str]:
        raise TorrcastError("служба раздач не отвечает")

    session = UnitPlaybackSession(
        configuration=lambda: wiring,
        state=lambda: wiring.state,
        active=lambda: False,
        unit_key=lambda: "",
        stop_unit=lambda: None,
        release_torrents=angry,
        cache_reserve=wiring._reserve,
        stream_address=wiring._address,
    )

    session.release(HASH)  # молчание вместо исключения и есть всё поведение

    assert wiring.released == []


def test_a_missing_address_does_not_cancel_the_status() -> None:
    wiring = _Wiring(fails=True)

    assert wiring.session().stream_address() == "адрес раздачи не определён"
    assert _Wiring().session().stream_address() == "http://10.0.0.7:8080"
    assert _Wiring().session().receiver_name() == "chromecast"
