"""Зеркало :mod:`torrcast.adapters.chromecast.mock.hls_decoder`."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import IO, Any

import pytest

from torrcast.adapters.chromecast.mock.hls_decoder import PROTOCOLS, HlsDecoder
from torrcast.domain.infra_error import InfraError
from torrcast.domain.position import Position
from torrcast.domain.reception_report import ReceptionReport

URL = "http://127.0.0.1:9/hls/index.m3u8"


def _manifest(spans: list[float], ended: bool = True) -> str:
    lines = ["#EXTM3U", "#EXT-X-PLAYLIST-TYPE:VOD"]
    for slot, span in enumerate(spans):
        lines += [f"#EXTINF:{span:.6f},", f"v{slot}.ts"]
    return "\n".join([*lines, *(["#EXT-X-ENDLIST"] if ended else []), ""])


class _Progress:
    """Декодер на бумаге: отдаёт строки ``-progress`` и закрывает вход нулём."""

    def __init__(self, lines: list[str]) -> None:
        self.stdout = iter(lines)
        self.code: int | None = None

    def poll(self) -> int | None:
        return self.code

    def wait(self, timeout: float | None = None) -> int:
        self.code = 0 if self.code is None else self.code  # снятый сигналом код не затирается
        return self.code

    def terminate(self) -> None:
        self.code = -15


def _no_ffmpeg(*args: Any, **kwargs: Any) -> Any:
    raise FileNotFoundError("ffmpeg")


def _err_of(decoder: HlsDecoder) -> IO[bytes] | None:
    """mypy сужает тип журнала по присваиванию и не сбрасывает сужение на вызовах методов."""
    return decoder.err


def test_the_head_of_the_playlist_is_cut_into_a_file_for_the_decoder() -> None:
    """Декодеру достаётся не адрес плейлиста, а плейлист со срезанной головой - файлом."""
    decoder = HlsDecoder(ReceptionReport())
    body = _manifest([10.023222, *[10.0] * 5])

    source, offset = decoder.source(URL, body, 25.0)

    assert source != URL and offset == pytest.approx(4.976778)
    lines = Path(source).read_text("utf-8").splitlines()
    assert [line for line in lines if not line.startswith("#")] == [
        f"http://127.0.0.1:9/hls/v{slot}.ts" for slot in (2, 3, 4, 5)
    ], "куски с нужного, адресами на ту же раздачу"
    decoder.close_log()


def test_there_is_nothing_to_cut_at_the_head_or_in_a_growing_manifest() -> None:
    """Вход остаётся прежним: с головы резать нечего, а растущий манифест резать нельзя."""
    decoder = HlsDecoder(ReceptionReport())
    spans = [10.0] * 6

    assert decoder.source(URL, _manifest(spans), 0.0) == (URL, 0.0)
    assert decoder.source(URL, _manifest(spans), 5.0) == (URL, 5.0)
    assert decoder.source(URL, _manifest(spans, ended=False), 25.0) == (URL, 25.0)
    assert decoder.playlist == "", "файла не заводилось - убирать нечего"


def test_the_cut_playlist_lives_exactly_one_pass_of_the_decoder() -> None:
    """Плейлист прошлого захода уходит вместе с заходом, а последний - вместе с журналом."""
    decoder = HlsDecoder(ReceptionReport())
    body = _manifest([10.0] * 6)

    first, _ = decoder.source(URL, body, 25.0)
    second, _ = decoder.source(URL, body, 45.0)

    assert not Path(first).exists(), "плейлист прошлого захода ушёл вместе с заходом"
    decoder.close_log()
    assert not Path(second).exists()
    assert decoder.playlist == ""


def test_a_playlist_from_a_file_gets_the_protocols_it_needs() -> None:
    """С диска наружу ffmpeg без списка протоколов не ходит - и вход не открывает вовсе."""
    seen: list[list[str]] = []
    decoder = HlsDecoder(ReceptionReport(), spawn=lambda command, **kwargs: seen.append(command))
    decoder.thread = lambda **kwargs: _Silent()

    decoder.open(URL, _manifest([10.0] * 6), 25.0)

    assert "-protocol_whitelist" in seen[0] and PROTOCOLS in seen[0]
    assert "-ss" in seen[0], "остаток внутрь куска декодер домотает сам"
    decoder.close_log()


class _Silent:
    """Поток, которого нет: читатель декодера тут не заводится."""

    def start(self) -> None:
        pass

    def join(self, timeout: float | None = None) -> None:
        pass


def test_a_missing_ffmpeg_is_named_and_the_journal_is_not_left_open() -> None:
    """ffmpeg не запустился - журнал держать не за кем, и об этом говорится вслух."""
    decoder = HlsDecoder(ReceptionReport(), spawn=_no_ffmpeg)
    left: IO[bytes] = tempfile.TemporaryFile()  # noqa: SIM115 - его закрытие и есть предмет
    decoder.err = left

    with pytest.raises(InfraError, match="ffmpeg"):
        decoder.open(URL, "", 0.0)

    assert left.closed, "журнал прошлого захода остался открытым"
    assert _err_of(decoder) is None


def test_the_follower_reads_the_position_and_counts_the_gaps() -> None:
    """Позиция берётся из ``-progress`` и считается от места захода, а разрывы - из журнала."""
    report = ReceptionReport()
    decoder = HlsDecoder(report)
    decoder.start = 1200.0
    decoder.pos = Position(1200.0, 0.0, True)
    decoder.proc = _Progress(["out_time_us=5000000\n", "out_time_us=12000000\n"])  # type: ignore[assignment]
    journal: IO[bytes] = tempfile.TemporaryFile()  # noqa: SIM115 - его закрывает сам читатель
    journal.write(b"[hls @ 0x1] Failed to open segment 7 of playlist 0\n")
    decoder.err = journal

    decoder.follow()

    assert decoder.pos.pos == 1212.0, "позиция абсолютная: место захода плюс время декодера"
    assert not decoder.pos.playing, "вход закрыт - картинки больше нет"
    assert report.decoded == 1212.0 and report.gaps == 1
    assert decoder.done.is_set() and _err_of(decoder) is None


def test_the_stop_takes_the_decoder_down_and_closes_the_journal() -> None:
    """Показ снимают - декодер получает сигнал, журнал закрывается, картинка гаснет."""
    decoder = HlsDecoder(ReceptionReport())
    decoder.pos = Position(600.0, 7200.0, True)
    decoder.proc = _Progress([])  # type: ignore[assignment]
    journal: IO[bytes] = tempfile.TemporaryFile()  # noqa: SIM115 - закрыть его и есть предмет
    decoder.err = journal

    decoder.stop()

    assert decoder.proc is not None and decoder.proc.poll() == -15
    assert journal.closed and _err_of(decoder) is None
    assert decoder.pos == Position(600.0, 7200.0, False), "место осталось, картинки нет"
    assert decoder.done.is_set()
