"""Проверяет подъём ленты фильма: сдвиг один на все заходы и считается с запасом."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from tests.conftest import module_of
from torrcast.adapters.stream_pack.pack_origin import _reorder_slack, _seconds, pack_origin
from torrcast.domain.hls_settings import AUDIO_PRIMING

module = module_of("torrcast.adapters.stream_pack.pack_origin")

URL = "http://торрент/поток?link=0123456789abcdef&index=0"


@pytest.fixture(autouse=True)
def _own_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "_ORIGIN", {})


def _probe(monkeypatch: pytest.MonkeyPatch, payload: Any) -> None:
    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if payload is None:
            raise OSError("ffprobe не дожил")
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(module.subprocess, "run", run)


def test_the_shift_is_measured_once_per_file(monkeypatch: pytest.MonkeyPatch) -> None:
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

    monkeypatch.setattr(module.subprocess, "run", run)
    first = pack_origin(URL)
    assert pack_origin(URL) == first
    assert len(counted) == 1, f"ffprobe позвали {len(counted)} раза на один файл"


def test_the_shift_is_rounded_up_to_the_millisecond(monkeypatch: pytest.MonkeyPatch) -> None:
    """В команду сдвиг уезжает с тремя знаками: округление вниз оставило бы метки ниже нуля
    на доли миллисекунды - то есть вернуло бы муксеру повод сдвинуть первый кусок самому.
    """
    _probe(monkeypatch, {"packets": [{"pts_time": "0.000", "dts_time": "-0.0801"}], "streams": []})
    assert pack_origin(URL) == 0.131
    assert pack_origin(URL) * 1000 == int(pack_origin(URL) * 1000)


def test_a_file_that_was_not_read_still_gets_the_priming_of_our_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Не прочли - остаётся набивка звука: гадать про видео нечем, а мёртвый вход не упакуется."""
    _probe(monkeypatch, None)
    assert pack_origin(URL) == pytest.approx(AUDIO_PRIMING)


def test_the_slack_is_the_largest_of_the_three_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ни один из трёх способов не работает на всех контейнерах, и берётся наибольшее.

    Переоценка стоит миллисекунд, недооценка возвращает дефект целиком.
    """
    _probe(
        monkeypatch,
        {
            "packets": [{"pts_time": "0.000", "dts_time": "-0.080"}],
            "streams": [{"has_b_frames": 3, "avg_frame_rate": "24/1"}],
        },
    )
    assert _reorder_slack(URL) == pytest.approx(0.125), "перестановка кадров тяжелее dts"


def test_a_measured_zero_is_not_the_same_as_no_measurement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 У mkv dts в файле нет вовсе, и первые два способа молчат: это не измеренный ноль."""
    _probe(monkeypatch, {"packets": [{"pts_time": "0.000", "dts_time": "N/A"}], "streams": []})
    assert _reorder_slack(URL) is None
    _probe(monkeypatch, {"packets": [{"pts_time": "0.000", "dts_time": "0.000"}], "streams": []})
    assert _reorder_slack(URL) == 0.0


def test_only_the_first_packet_tells_about_the_reordering(monkeypatch: pytest.MonkeyPatch) -> None:
    """⚠️ У пакетов в середине ``pts - dts`` - глубина перестановки вообще (до 0.417 по фильму),
    и брать её значило бы сдвигать ленту на полсекунды там, где хватает двух кадров.
    """
    _probe(
        monkeypatch,
        {
            "packets": [
                {"pts_time": "0.000", "dts_time": "-0.083"},
                {"pts_time": "0.500", "dts_time": "0.083"},
            ],
            "streams": [],
        },
    )
    assert _reorder_slack(URL) == pytest.approx(0.083)


def test_a_field_of_ffprobe_is_a_number_or_a_fraction_or_nothing() -> None:
    """``avg_frame_rate`` приходит дробью, ``N/A`` - словом, а поля может не быть вовсе."""
    assert _seconds("24/1") == 24.0
    assert _seconds("0.080") == 0.08
    assert _seconds("N/A") is None
    assert _seconds("0/0") is None
    assert _seconds(None) is None and _seconds(3) is None
