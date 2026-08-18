"""Зеркало показа целиком: тракт поднялся, LOAD ушёл, хозяйство погасло в любом исходе."""

from __future__ import annotations

from pathlib import Path

import pytest

import torrcast.usecases.playback._show_state as _state
import torrcast.usecases.revive_playback._revive_state as _revive
from tests.fakes.clock import FakeClock
from tests.usecases.playback.world import film_keys
from torrcast.adapters.http_server.hls_server import HlsServer
from torrcast.adapters.stream_pack.grid_for import grid_for
from torrcast.adapters.stream_pack.hls_dir import hls_dir
from torrcast.domain.config import Config
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.position import Position
from torrcast.domain.start_refused_error import StartRefusedError
from torrcast.recode import Encode, Recoder, Weights, whole_encode
from torrcast.usecases.playback._play import _play
from torrcast.usecases.start_clock import _Clock


class _Screening:
    """Приёмник по сценарию: взял LOAD, показал кадр и погас."""

    def __init__(self, refuse: bool = False) -> None:
        self.refuse = refuse
        self.loaded: list[tuple[str, float]] = []
        self.script = [(10.0, "PLAYING"), (12.0, "PLAYING"), (-1.0, "IDLE")]
        self.quit: list[bool] = []
        self.next_cut = None

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        if self.refuse:
            raise StartRefusedError("приёмник LOAD не взял")
        self.loaded.append((url, at))

    def stop(self, quit_app: bool = False) -> None:
        self.quit.append(quit_app)

    def position(self, front: float = 0.0) -> Position:
        pos, state = self.script.pop(0) if self.script else (0.0, "IDLE")
        return Position(pos, 300.0, state in {"PLAYING", "BUFFERING"}, state)

    def replay(self, pos: float) -> float:
        return -1.0


@pytest.fixture(autouse=True)
def _world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_state, "film_keys", lambda source: film_keys())
    monkeypatch.setattr(_state, "weights_of", Weights.of)
    monkeypatch.setattr(_state, "Recoder", Recoder)
    monkeypatch.setattr(_state, "Encode", Encode)
    monkeypatch.setattr(_state, "whole_encode", whole_encode)
    monkeypatch.setattr(_state, "grid_for", grid_for)
    monkeypatch.setattr(_state, "HlsServer", HlsServer)
    monkeypatch.setattr(_state, "RECODE_DIR", "recode")
    monkeypatch.setattr(_state, "hls_dir", lambda where: hls_dir(str(where)))
    monkeypatch.setattr(_state, "hls_base", lambda config: "http://127.0.0.1:0")
    # Часы держателя показа - ручные: зеркало меряет решение показа, а не терпеливость
    # машины. С боевыми часами круг опроса ждал бы настоящие две секунды на каждый шаг.
    monkeypatch.setattr(_revive, "_revive_clock", FakeClock(now=1000.0))
    monkeypatch.setattr(_revive, "_revive_playing_mark", lambda where: None)


def _config(tmp_path: Path) -> Config:
    return Config(recode=False, warm=False, hls_dir=str(tmp_path / "hls"), hls_port=0)


def test_the_show_loads_the_manifest_and_ends_by_itself(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """LOAD уходит манифестом с нужного места, а погасший экран кончает показ."""
    receiver = _Screening()

    code = _play(_config(tmp_path), "file:///нет-такого", 0, "«Кино»", _Clock(), receiver=receiver)

    assert code == EXIT_OK
    assert receiver.loaded and receiver.loaded[0][0].endswith("/index.m3u8")
    assert receiver.quit, "показ кончился - приложение приёмника закрывается"
    assert "играю «Кино»" in capsys.readouterr().out


def test_a_refused_load_is_not_a_funeral(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Отказ на первом LOAD показ не хоронит - его поднимает лестница воскрешения."""
    receiver = _Screening(refuse=True)

    code = _play(_config(tmp_path), "file:///нет-такого", 0, "«Кино»", _Clock(), receiver=receiver)

    assert code == EXIT_OK
    assert "поднимаю показ сам" in capsys.readouterr().out


def test_the_grid_is_named_to_the_receiver(tmp_path: Path) -> None:
    """Приёмник спотыкается о сетку - и показ обязан назвать её ему на каждой серии."""
    receiver = _Screening()

    _play(_config(tmp_path), "file:///нет-такого", 0, "«Кино»", _Clock(), receiver=receiver)

    assert receiver.next_cut is not None
