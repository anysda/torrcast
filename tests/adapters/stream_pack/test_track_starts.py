"""Проверяет замер места обеих дорожек куска без запуска ffprobe."""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any

from torrcast.adapters.stream_pack.track_starts import track_starts

_PIECE = Path("/кусок.ts")


class _Answer:
    def __init__(self, out: str) -> None:
        self.stdout = out.encode("utf-8")
        self.returncode = 0


def _probe(*packets: tuple[int, str], streams: tuple[tuple[int, str], ...] | None = None) -> Any:
    """Ответ ffprobe: потоки и их пакеты в том виде, в каком он их печатает."""
    kinds = streams if streams is not None else ((0, "video"), (1, "audio"))
    payload = {
        "streams": [{"index": index, "codec_type": kind} for index, kind in kinds],
        "packets": [{"stream_index": index, "pts_time": mark} for index, mark in packets],
    }
    return lambda *a, **k: _Answer(json.dumps(payload))


def test_both_marks_come_back_as_they_stand_on_the_tape() -> None:
    """Отдаются обе метки как есть: сравнивает их с границей слота вызывающий, не проба."""
    assert track_starts(_PIECE, run=_probe((0, "10.144000"), (1, "10.075333"))) == (
        10.144,
        10.075333,
    )


def test_the_first_packet_of_each_track_is_the_one_that_counts() -> None:
    """Меряются ПЕРВЫЕ пакеты дорожек, а не любые: дальше метки уже разошлись по кадрам."""
    marks = track_starts(_PIECE, run=_probe((1, "10.000"), (0, "10.100"), (1, "10.021")))
    assert marks == (10.1, 10.0)


def test_a_track_missing_from_the_head_is_not_a_number() -> None:
    """🔴 TC-833. Дорожки в голове нет - ``nan``: на своём месте её точно нет.

    Ровно так выглядит поломка на сдвиге в сотни секунд: голова состоит из одного видео
    целиком, и второй дорожки в ней не встречается вовсе.
    """
    picture, sound = track_starts(_PIECE, run=_probe((0, "10.0")))
    assert picture == 10.0 and math.isnan(sound)
    picture, sound = track_starts(_PIECE, run=_probe((1, "10.0")))
    assert math.isnan(picture) and sound == 10.0


def test_a_container_ffprobe_could_not_open_gives_two_silences() -> None:
    """Голый фрагмент fMP4 без своего заголовка ffprobe не разбирает - честное «не знаю»."""
    assert all(math.isnan(mark) for mark in track_starts(_PIECE, run=lambda *a, **k: _Answer("")))


def test_a_probe_that_never_ran_gives_two_silences() -> None:
    """Нет ffprobe или он не успел - обе метки ``nan``; решает по ним вызывающий."""

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=1.0)

    assert all(math.isnan(mark) for mark in track_starts(_PIECE, run=broken))


def test_marks_that_are_not_numbers_do_not_pass_for_a_measurement() -> None:
    """``N/A`` в метке - это не ноль: такой пакет пропускается, как будто его нет."""
    picture, sound = track_starts(_PIECE, run=_probe((0, "10.0"), (1, "N/A")))
    assert picture == 10.0 and math.isnan(sound)


def test_a_piece_with_no_tracks_at_all_gives_two_silences() -> None:
    """Ни одной дорожки в куске - сверять нечего ни с той, ни с другой стороны."""
    assert all(math.isnan(mark) for mark in track_starts(_PIECE, run=_probe(streams=())))


def test_only_the_head_of_the_piece_is_read() -> None:
    """Проба читает голову и только её: цена не должна зависеть от веса куска."""
    seen: list[list[str]] = []

    def spy(command: list[str], **kwargs: Any) -> Any:
        seen.append(command)
        return _Answer("{}")

    track_starts(_PIECE, run=spy)
    assert "-read_intervals" in seen[0], seen[0]
    assert seen[0][seen[0].index("-read_intervals") + 1].startswith("%+#"), seen[0]


def _split(head: Any, apart: dict[str, str]) -> Any:
    """Ffprobe, который на голову отвечает одним, а на вопрос дорожке порознь - другим."""

    def run(command: list[str], **kwargs: Any) -> Any:
        if "-select_streams" in command:
            return _Answer(apart.get(command[command.index("-select_streams") + 1], ""))
        return head(command, **kwargs)

    return run


def test_a_track_that_the_head_did_not_reach_is_asked_about_directly() -> None:
    """🔴 На CMAF без этого меры нет вовсе: голова в сорок пакетов до картинки не достаёт.

    Пакеты муксер отдаёт по возрастанию метки, а счётчики дорожек куска CMAF свои: на живом
    куске показа звук стоит на 49.792, картинка - на 59.809, и все 467 пакетов звука выходят
    ПЕРЕД первым пакетом картинки.
    """
    marks = track_starts(
        _PIECE, run=_split(_probe((1, "49.792000")), {"v": "59.893000\n59.935000\n"})
    )

    assert marks == (59.893, 49.792)


def test_the_track_found_in_the_head_is_not_asked_a_second_time() -> None:
    """Вопрос порознь стоит 0.15 с и задаётся только там, где в голове дорожки не нашлось."""
    asked: list[str] = []

    def run(command: list[str], **kwargs: Any) -> Any:
        asked.append(" ".join(command))
        return _probe((0, "10.144000"), (1, "10.075333"))(command, **kwargs)

    assert track_starts(_PIECE, run=run) == (10.144, 10.075333)
    assert len(asked) == 1


def test_a_track_that_answers_nothing_even_apart_stays_not_a_number() -> None:
    """Дорожки нет в куске вовсе - ``nan``, и решает по нему отказом вызывающий."""
    picture, sound = track_starts(_PIECE, run=_split(_probe((1, "10.0")), {"v": ""}))

    assert math.isnan(picture) and sound == 10.0


def test_the_piece_asked_about_may_be_a_reading_protocol_and_not_a_file() -> None:
    """Голый кусок CMAF читается только вместе со своим заголовком, а это ``concat:``."""
    seen: list[str] = []

    def run(command: list[str], **kwargs: Any) -> Any:
        seen.append(command[-1])
        return _probe((0, "1.0"), (1, "1.0"))(command, **kwargs)

    track_starts("concat:/init.mp4|/кусок.m4s", run=run)

    assert seen == ["concat:/init.mp4|/кусок.m4s"]
