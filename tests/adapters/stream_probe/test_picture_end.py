"""Конец картинки в паспорте: сетка показа не обещает кусков за последним кадром."""

from __future__ import annotations

import json
import math
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from tests.usecases.feed_pack.world import FakeProc, packer
from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.packer_finished import _finished
from torrcast.adapters.stream_pack.piece_overhang import piece_overhang
from torrcast.adapters.stream_probe.picture_end import PAST_END, picture_end
from torrcast.adapters.stream_probe.probe import probe
from torrcast.domain.segment_container import FMP4
from torrcast.domain.swarm_error import SwarmError

if TYPE_CHECKING:
    from pathlib import Path

_HEAD = json.dumps({"format": {"duration": "2702.688"}, "streams": [
    {"index": 0, "codec_name": "h264", "codec_type": "video", "width": 1280, "height": 720},
    {"index": 1, "codec_name": "ac3", "codec_type": "audio", "channels": 6},
]})  # fmt: skip


def _stream(tail: str, seen: list[list[str]] | None = None) -> Any:
    """Поток: голове отвечает паспортом, хвосту - пакетами видео ``tail``."""

    def run(command: list[str], timeout: float, alive: Any) -> str:
        if seen is not None:
            seen.append(command)
        return _HEAD if "-seekable" in command else tail

    return run


def test_the_tail_is_read_past_any_end_by_picture_packets_only() -> None:
    """Длительности заранее нет - хвост читается одновременно с головой, перемоткой за конец."""
    seen: list[list[str]] = []
    end = picture_end("http://torr/s", 8.0, None, _stream("2588.464,0.040\n2580.0,N/A\n", seen))
    assert end == pytest.approx(2588.504)
    command = seen[0]
    assert command[command.index("-read_intervals") + 1] == PAST_END
    assert command[command.index("-select_streams") + 1] == "V:0", "обложка - не картинка"
    assert "-seekable" not in command, "перемотка по индексу файла и есть способ"
    assert command[-1] == "http://torr/s"


@pytest.mark.parametrize(
    "fault",
    [OSError("ffprobe"), subprocess.TimeoutExpired("ffprobe", 8.0), SwarmError("рой молчит"),
     subprocess.CalledProcessError(1, "ffprobe")],
)  # fmt: skip
def test_an_unread_tail_is_an_honest_unknown(fault: Exception) -> None:
    """Хвост не дался - ``nan``, и показ остаётся на длительности контейнера, как было."""

    def run(*_a: object) -> str:
        raise fault

    assert math.isnan(picture_end("http://torr/s", 8.0, None, run))
    assert math.isnan(picture_end("http://torr/s", 8.0, None, _stream("N/A,N/A\n")))


def test_the_passport_carries_the_picture_end_and_keeps_it_on_the_shelf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 «Отчаянные домохозяйки» s3, WEB-DL 720p: видео до 2588.5 с, звук и контейнер до 2702.7.

    Сетка до конца контейнера ждала куска 258 и дальше, которых упаковка не режет: приёмник
    стоял на 2579.5, потом ошибка и ложное «досмотрено». Отрицательная проба: паспорт без
    :func:`to_picture` - длительность 2702.688, тест красный.
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    media = probe("http://torr/stream/hash-dh/2", run=_stream("2588.464,0.040\n"))
    assert media.duration == pytest.approx(2588.504)

    def boom(*_a: object) -> str:
        raise AssertionError("паспорт обязан прийти с полки")

    assert probe("http://torr/stream/hash-dh/2", run=boom).duration == pytest.approx(2588.504)


@pytest.mark.ffmpeg
def test_a_real_file_whose_sound_outlasts_the_picture_packs_to_its_last_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Настоящий файл в малом: картинка 20 с, звук 30 с. Паспорт - конец картинки, и
    прогон упаковки доходит до последнего слота сетки, а звук за кадром не тянется в хвост.

    Отрицательная проба: длительность по контейнеру - сетка ждёт слот 20-30 с, которого
    нет, и прогон назван недочитанным (дефект стенда в малом).
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    source = tmp_path / "short-picture.mkv"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=20",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=30", "-c:v", "libx264", "-g", "25",
         "-preset", "ultrafast", "-c:a", "aac", str(source)],
        check=True, capture_output=True,
    )  # fmt: skip
    media = probe(str(source))
    assert media.duration == pytest.approx(20.0, abs=0.1)
    grid = Grid.uniform(media.duration, 10.0)
    state = packer(tmp_path, grid=grid, container=FMP4, proc=FakeProc(code=0))
    command = ffmpeg_pack_command(
        str(source), 0, str(state.run), grid, 0, 0.0, readrate=0.0, container=FMP4
    )
    subprocess.run(command, check=True, capture_output=True)
    assert _finished(state) is True, "хвост по картинке назван обрывом"
    last = state.run / f"v{grid.count - 1}.m4s"
    over = piece_overhang(last, state.run / "init.mp4")
    assert over < 1.5, f"звук за кадром уехал в хвост: {over:.1f} с после последнего кадра"
