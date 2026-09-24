"""Щуп паспорта: один запрос к ffprobe, полка вместо второго и понятная беда вместо трейсбека."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from torrcast.adapters.stream_probe.probe import Runner, probe
from torrcast.domain.infra_error import InfraError

if TYPE_CHECKING:
    from pathlib import Path

_ANSWER = json.dumps(
    {
        "format": {"duration": "3600.0"},
        "streams": [
            {
                "index": 0,
                "codec_name": "h264",
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "profile": "High 10",
                "pix_fmt": "yuv420p10le",
                "color_transfer": "smpte2084",
                "field_order": "progressive",
            },
            {
                "index": 1,
                "codec_name": "eac3",
                "codec_type": "audio",
                "channels": 6,
                "tags": {"language": "rus", "title": "дубляж"},
            },
        ],
    }
)


def _asked(seen: list[list[str]], answer: str = _ANSWER) -> Runner:
    """Запуск ffprobe, который ничего не запускает: собирает команды и отвечает готовым."""

    def _run(command: list[str], timeout: float, alive: Any) -> str:
        seen.append(command)
        return answer

    return _run


def test_the_whole_passport_is_taken_by_one_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Формат кадра, кривая яркости и развёртка берутся тем же одним запросом и даром."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    seen: list[list[str]] = []

    media = probe("http://torr/stream/hash-1/2", run=_asked(seen))

    assert len(seen) == 1, "один ffprobe на файл, и только один"
    flags = " ".join(seen[0])
    for field in ("profile", "pix_fmt", "color_transfer", "field_order", "stream_tags"):
        assert field in flags, f"{field} берётся тем же запросом"
    assert media.duration == 3600.0
    assert media.tracks[0].language == "rus" and media.tracks[0].channels == 6


def test_the_http_probe_cannot_jump_to_the_torrent_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cues/Tags в конце mkv не нужны дорожкам, а холодный хвост стоит отдельного куска роя."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    seen: list[list[str]] = []
    url = "http://torr/stream/hash-tail/2"

    probe(url, run=_asked(seen))

    seek = seen[0].index("-seekable")
    assert seen[0][seek : seek + 2] == ["-seekable", "0"]
    assert seek < seen[0].index(url), "это опция входа, после URL она его уже не ограничит"


def test_the_second_ask_comes_from_the_shelf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Первое чтение стоит роя - до 17 с; и без сети длительность серии всё равно нужна."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    seen: list[list[str]] = []
    run = _asked(seen)

    first = probe("http://torr/stream/hash-1/2", run=run)
    cached = probe("http://torr/stream/hash-1/2", run=run)

    assert len(seen) == 1, "второй раз ffprobe не зовут"
    assert cached == first


def test_a_missing_ffprobe_is_named_not_traced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Человеку нужна причина, а не трейсбек: беда среды называется словами."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))

    def _gone(command: list[str], timeout: float, alive: Any) -> str:
        raise FileNotFoundError(command[0])

    with pytest.raises(InfraError, match="ffprobe is not installed"):
        probe("http://torr/stream/hash-1/2", run=_gone)


def test_a_stream_that_never_came_is_told_apart_from_a_broken_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """«Не дождался потока» и «не прочитал поток» - разные беды и разные советы."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))

    def _late(command: list[str], timeout: float, alive: Any) -> str:
        raise subprocess.TimeoutExpired(command, timeout)

    with pytest.raises(InfraError, match="did not wait for the stream"):
        probe("http://torr/stream/hash-1/2", run=_late)

    def _bad(command: list[str], timeout: float, alive: Any) -> str:
        raise subprocess.CalledProcessError(1, command, "", "moov atom not found")

    with pytest.raises(InfraError, match="moov atom not found"):
        probe("http://torr/stream/hash-1/3", run=_bad)


def test_a_failed_probe_leaves_no_record_on_the_shelf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Осечка одного запуска не имеет права стать вечной."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    empty = _asked([], answer=json.dumps({"format": {}, "streams": []}))

    probe("http://torr/stream/hash-1/2", run=empty)
    seen: list[list[str]] = []
    probe("http://torr/stream/hash-1/2", run=_asked(seen))

    assert len(seen) == 1, "пустой паспорт на полку не лёг - спросили заново"
