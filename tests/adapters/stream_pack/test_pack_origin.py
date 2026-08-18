"""Проверяет подъём ленты фильма: сдвиг один на все заходы и считается с запасом."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from torrcast.adapters.pack_memory import _ORIGIN
from torrcast.adapters.stream_pack.pack_origin import _reorder_slack, _seconds, pack_origin
from torrcast.domain.hls_settings import AUDIO_PRIMING

URL = "http://торрент/поток?link=0123456789abcdef&index=0"


@pytest.fixture(autouse=True)
def _own_memory() -> Iterator[None]:
    """Память сдвига живёт на весь процесс; каждой пробе она достаётся пустой."""
    _ORIGIN.clear()
    yield
    _ORIGIN.clear()


def _probe(payload: Any) -> Callable[..., subprocess.CompletedProcess[str]]:
    """Ответ ffprobe готовой строкой; ``None`` - ffprobe не дожил."""

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if payload is None:
            raise OSError("ffprobe не дожил")
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    return run


def test_the_shift_is_measured_once_per_file() -> None:
    """🔴 Заходов на фильм много - старт, перемотка, прогрев, перекод, - а сдвиг у них ОДИН.

    Разъедься он, и заход, упаковавший без сдвига, поставил бы на стыке с чужим ход
    меток НАЗАД: ``Parsed buffers not in DTS sequence`` и мёртвый показ.
    """
    counted: list[int] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        counted.append(1)
        return subprocess.CompletedProcess(
            command, 0, json.dumps({"packets": [], "streams": []}), ""
        )

    def slack(url: str, timeout: float) -> float | None:
        return _reorder_slack(url, timeout, run=run)

    first = pack_origin(URL, slack_of=slack)
    assert pack_origin(URL, slack_of=slack) == first
    assert len(counted) == 1, f"ffprobe позвали {len(counted)} раза на один файл"


def test_the_shift_is_rounded_up_to_the_millisecond() -> None:
    """В команду сдвиг уезжает с тремя знаками: округление вниз оставило бы метки ниже нуля
    на доли миллисекунды - то есть вернуло бы муксеру повод сдвинуть первый кусок самому.
    """
    run = _probe({"packets": [{"pts_time": "0.000", "dts_time": "-0.0801"}], "streams": []})
    shift = pack_origin(URL, slack_of=lambda url, timeout: _reorder_slack(url, timeout, run=run))
    assert shift == 0.131
    assert shift * 1000 == int(shift * 1000)


def test_a_file_that_was_not_read_still_gets_the_priming_of_our_audio() -> None:
    """Не прочли - остаётся набивка звука: гадать про видео нечем, а мёртвый вход не упакуется."""
    run = _probe(None)
    shift = pack_origin(URL, slack_of=lambda url, timeout: _reorder_slack(url, timeout, run=run))
    assert shift == pytest.approx(AUDIO_PRIMING)


def test_the_slack_is_the_largest_of_the_three_answers() -> None:
    """Ни один из трёх способов не работает на всех контейнерах, и берётся наибольшее.

    Переоценка стоит миллисекунд, недооценка возвращает дефект целиком.
    """
    run = _probe(
        {
            "packets": [{"pts_time": "0.000", "dts_time": "-0.080"}],
            "streams": [{"has_b_frames": 3, "avg_frame_rate": "24/1"}],
        }
    )
    assert _reorder_slack(URL, run=run) == pytest.approx(0.125), "перестановка кадров тяжелее dts"


def test_a_measured_zero_is_not_the_same_as_no_measurement() -> None:
    """🔴 У mkv dts в файле нет вовсе, и первые два способа молчат: это не измеренный ноль."""
    silent = _probe({"packets": [{"pts_time": "0.000", "dts_time": "N/A"}], "streams": []})
    assert _reorder_slack(URL, run=silent) is None
    zero = _probe({"packets": [{"pts_time": "0.000", "dts_time": "0.000"}], "streams": []})
    assert _reorder_slack(URL, run=zero) == 0.0


def test_only_the_first_packet_tells_about_the_reordering() -> None:
    """⚠️ У пакетов в середине ``pts - dts`` - глубина перестановки вообще (до 0.417 по фильму),
    и брать её значило бы сдвигать ленту на полсекунды там, где хватает двух кадров.
    """
    run = _probe(
        {
            "packets": [
                {"pts_time": "0.000", "dts_time": "-0.083"},
                {"pts_time": "0.500", "dts_time": "0.083"},
            ],
            "streams": [],
        }
    )
    assert _reorder_slack(URL, run=run) == pytest.approx(0.083)


def test_a_field_of_ffprobe_is_a_number_or_a_fraction_or_nothing() -> None:
    """``avg_frame_rate`` приходит дробью, ``N/A`` - словом, а поля может не быть вовсе."""
    assert _seconds("24/1") == 24.0
    assert _seconds("0.080") == 0.08
    assert _seconds("N/A") is None
    assert _seconds("0/0") is None
    assert _seconds(None) is None and _seconds(3) is None
