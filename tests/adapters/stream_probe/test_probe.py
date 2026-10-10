"""Щуп паспорта: один запрос к ffprobe, полка вместо второго и понятная беда вместо трейсбека."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from torrcast.adapters.stream_probe.probe import Runner, probe
from torrcast.adapters.torrserver.stream_reads import READS
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


#: Хвост обычного файла (:func:`picture_end`): картинка до конца контейнера, файл дочитан.
_TAIL = "video,3599.96,0.04\naudio,3599.968,0.032\n"


def _asked(seen: list[list[str]], answer: str = _ANSWER, tail: str = _TAIL) -> Runner:
    """Запуск ffprobe, который ничего не запускает: собирает команды и отвечает готовым."""

    def _run(command: list[str], timeout: float, alive: Any) -> str:
        seen.append(command)
        return answer if "-seekable" in command else tail

    return _run


def test_the_whole_passport_is_taken_by_one_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Формат кадра, кривая яркости и развёртка берутся тем же одним запросом и даром."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    seen: list[list[str]] = []

    media = probe("http://torr/stream/hash-1/2", run=_asked(seen))

    heads = [command for command in seen if "-seekable" in command]
    assert len(heads) == 1, "голова паспорта - одним ffprobe на файл, и только одним"
    assert len(seen) == 2, "вторым идёт только хвост с концом картинки"
    flags = " ".join(heads[0])
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

    head = next(command for command in seen if "format=duration" in " ".join(command))
    seek = head.index("-seekable")
    assert head[seek : seek + 2] == ["-seekable", "0"]
    assert seek < head.index(url), "это опция входа, после URL она его уже не ограничит"


def test_the_second_ask_comes_from_the_shelf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Первое чтение стоит роя - до 17 с; и без сети длительность серии всё равно нужна."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    seen: list[list[str]] = []
    run = _asked(seen)

    first = probe("http://torr/stream/hash-1/2", run=run)
    cached = probe("http://torr/stream/hash-1/2", run=run)

    assert len(seen) == 2, "второй раз ffprobe не зовут: ни голову, ни хвост"
    assert cached == first


def test_a_passport_whose_tail_was_not_read_stays_off_the_shelf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 Хвост не дочитался - длительность по контейнеру только на этот раз, а не навсегда.

    Стенд: холодный рой не отдал хвост за бюджет, полка запомнила 2702.7 вместо 2588.5,
    и все следующие запуски серии снова ждали кусков за последним кадром. Отрицательная
    проба: класть паспорт на полку всегда - второй щуп не зовёт ffprobe, тест красный.
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    seen: list[list[str]] = []

    first = probe("http://torr/stream/hash-1/2", run=_asked(seen, tail=""))
    again = probe("http://torr/stream/hash-1/2", run=_asked(seen))

    assert first.duration == again.duration == 3600.0
    assert len(seen) == 4, "второй щуп обязан спросить хвост снова"
    third = probe("http://torr/stream/hash-1/2", run=_asked(seen))
    assert third == again and len(seen) == 4, "дочитанный хвост ложится на полку"


def test_a_voice_file_passport_reaches_the_shelf_without_a_picture_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Внешняя озвучка картинки не несёт, и конца картинки у неё не бывает вовсе.

    Паспорт звука следующей серии автопереход посреди обрыва берёт только с полки
    (:func:`torrcast.usecases.episode_duration._duration`). Отрицательная проба: убрать
    ветку файла без видео - второй щуп зовёт ffprobe, тест красный.
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    voice = json.dumps(
        {
            "format": {"duration": "2702.688"},
            "streams": [{"index": 0, "codec_name": "ac3", "codec_type": "audio", "channels": 6}],
        }
    )
    tail = "".join(f"audio,{2690 + 0.032 * n:.3f},0.032\n" for n in range(300))

    first = probe("http://torr/stream/hash-voice/3", run=_asked([], answer=voice, tail=tail))

    def boom(*_a: object) -> str:
        raise AssertionError("паспорт озвучки обязан прийти с полки")

    assert probe("http://torr/stream/hash-voice/3", run=boom) == first


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

    assert len(seen) == 2, "пустой паспорт на полку не лёг - спросили заново"


def test_ffprobe_holds_the_torrent_until_its_process_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Снос соседа не имеет права послать ``rem`` между стартом ffprobe и его выходом."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    key = "0123456789abcdef0123456789abcdef01234567"
    url = f"http://torr/stream?link={key}&index=1&play"

    def held(command: list[str], timeout: float, alive: Any) -> str:
        assert READS.close(key), "ffprobe не встал читателем /stream"
        assert READS.busy(key)
        return _ANSWER

    try:
        probe(url, run=held)
        assert not READS.busy(key)
    finally:
        READS.reopen(key)


def test_ffprobe_stops_when_its_stream_read_is_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Срок снятия раздачи должен остановить ffprobe тем же callback, что и мёртвый рой."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    key = "1123456789abcdef0123456789abcdef01234567"
    url = f"http://torr/stream?link={key}&index=1&play"

    def stopped(command: list[str], timeout: float, alive: Any) -> str:
        assert READS.close(key), "ffprobe не встал читателем /stream"
        READS.stop(key)
        assert alive is not None and not alive(), "ffprobe не увидел срок чтения"
        return _ANSWER

    try:
        probe(url, run=stopped)
    finally:
        READS.reopen(key)
