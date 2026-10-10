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
from torrcast.adapters.stream_probe.picture_end import PACKETS, PAST_END, picture_end
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


#: Хвост «Отчаянных домохозяек» s3e2, как его отдал стенд: последний опорный кадр 2587.504,
#: картинка до 2588.504, два русских звука идут дальше, файл не дочитан (окно полное).
_DH = "\n".join(
    ["video,2587.504,0.040", "audio,2587.584,0.032", "video,2588.464,0.040"]
    + [f"audio,{2588.0 + 0.032 * n:.3f},0.032" for n in range(PACKETS - 3)]
)


def test_the_tail_is_read_past_any_end_within_a_bounded_window() -> None:
    """Длительности заранее нет - хвост читается одновременно с головой, перемоткой за
    конец, и не до конца файла: звук за последним кадром тянется минутами.

    Отрицательная проба: читать без предела пакетов - 65 МБ звука из холодного роя, и на
    стенде хвост не узнавался ни разу; тест красный на команде.
    """
    seen: list[list[str]] = []
    end = picture_end("http://torr/s", 8.0, None, _stream(_DH, seen))
    assert end == pytest.approx(2588.504)
    command = seen[0]
    assert command[command.index("-read_intervals") + 1] == f"{PAST_END}+#{PACKETS}"
    assert "-select_streams" not in command, "звук нужен окну, чтобы назвать конец картинки"
    assert "-seekable" not in command, "перемотка по индексу файла и есть способ"
    assert command[-1] == "http://torr/s"


def test_a_window_that_ends_inside_the_picture_trims_nothing() -> None:
    """Окно кончилось, а кадры идут вровень со звуком - картинка не короче звука.

    Отрицательная проба: назвать концом последний кадр окна - сетка обрезала бы фильм.
    """
    tail = "\n".join(
        f"{kind},{3000.0 + 0.02 * n:.2f},0.020"
        for n in range(PACKETS)
        for kind in ["video" if n % 2 else "audio"]
    )
    assert picture_end("http://torr/s", 8.0, None, _stream(tail)) == math.inf


def test_a_read_to_the_end_of_the_file_names_the_last_frame() -> None:
    """Файл дочитан в окне - последний кадр и есть конец, даже без звука за ним."""
    tail = "video,5398.0,0.040\naudio,5398.5,0.032\nvideo,5399.96,0.040\n"
    assert picture_end("http://torr/s", 8.0, None, _stream(tail)) == pytest.approx(5400.0)


def test_a_cover_image_stamped_at_zero_is_not_the_picture() -> None:
    """Обложка mkv - тоже «видео», с меткой ноль: концом картинки она не становится."""
    assert math.isnan(
        picture_end("http://torr/s", 8.0, None, _stream("video,0.0,0.040\naudio,5398.5,0.032\n"))
    )
    tail = "video,0.0,0.040\n" + _DH
    assert picture_end("http://torr/s", 8.0, None, _stream(tail)) == pytest.approx(2588.504)


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
    assert math.isnan(picture_end("http://torr/s", 8.0, None, _stream("video,N/A,N/A\n")))
    assert math.isnan(picture_end("http://torr/s", 8.0, None, _stream("")))


def test_the_passport_carries_the_picture_end_and_keeps_it_on_the_shelf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 «Отчаянные домохозяйки» s3, WEB-DL 720p: видео до 2588.5 с, звук и контейнер до 2702.7.

    Сетка до конца контейнера ждала куска 258 и дальше, которых упаковка не режет: приёмник
    стоял на 2579.5, потом ошибка и ложное «досмотрено». Отрицательная проба: паспорт без
    :func:`to_picture` - длительность 2702.688, тест красный.
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    media = probe("http://torr/stream/hash-dh/2", run=_stream(_DH))
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


@pytest.mark.ffmpeg
def test_a_real_file_whose_sound_runs_minutes_past_the_picture_is_read_only_to_its_window(
    tmp_path: Path,
) -> None:
    """Настоящий ffprobe: картинка 20 с, звук 200 с - окно в :data:`PACKETS` пакетов
    кончается задолго до конца файла и всё равно называет конец картинки.

    Дорожки сводятся готовыми, как в раздачах: прямой прогон ffmpeg дописывает последние
    кадры кодировщика в конец файла, за весь звук, и окно их не видит.
    """
    video, sound, source = tmp_path / "v.mkv", tmp_path / "a.mka", tmp_path / "long-sound.mkv"
    lavfi = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i"]
    picture = ["testsrc2=size=160x90:rate=25:duration=20", "-c:v", "libx264", "-g", "25"]
    mux = ["-i", str(video), "-i", str(sound), "-map", "0", "-map", "1", "-c", "copy"]
    for command in (
        [*lavfi, *picture, "-preset", "ultrafast", str(video)],
        [*lavfi, "sine=frequency=440:duration=200", "-c:a", "aac", str(sound)],
        ["ffmpeg", "-v", "error", *mux, str(source)],
    ):
        subprocess.run(command, check=True, capture_output=True)
    seen: list[str] = []

    def run(command: list[str], timeout: float, alive: Any) -> str:
        out = subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
        seen.append(out.stdout)
        return out.stdout

    assert picture_end(str(source), 30.0, None, run) == pytest.approx(20.0, abs=0.05)
    assert len(seen[0].splitlines()) == PACKETS, "файл дочитан до конца - окна нет"
