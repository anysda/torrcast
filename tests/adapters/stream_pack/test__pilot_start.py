"""Проверяет пробный прогон: ответ переводится в ленту фильма, а уезд вперёд остаётся."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.conftest import CLIP_KEY_SECONDS, CLIP_RATE
from tests.fakes.journal import Tape
from torrcast.adapters.stream_pack._pilot_start import _FILM_START, _film_start, _pilot_start

#: На столько уезжает вперёд лента контейнера в фикстуре ниже.
SHIFT = 600.0


@pytest.fixture(autouse=True)
def _own_memory() -> Iterator[None]:
    """Начало ленты помнится на весь процесс; каждой проверке нужна своя память."""
    _FILM_START.clear()
    yield
    _FILM_START.clear()


@pytest.fixture
def clip_shifted(clip: str, tmp_path: Path) -> str:
    """Тот же ролик в mpegts, чьи метки начинаются не с нуля - так лежат .ts и .m2ts."""
    path = tmp_path / "shifted.ts"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", clip,
         "-c", "copy", "-output_ts_offset", f"{SHIFT:g}",
         "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", "-y", str(path)],
        check=True, capture_output=True,
    )  # fmt: skip
    return str(path)


@pytest.fixture
def clip_mp4_late_start(tmp_path: Path) -> str:
    """mp4, чьё видео начинается не с нуля: у исходника звук начался на набивку aac раньше.

    Так лежат ремуксы mkv в mp4 (замер TC-699: ``start_time`` видео 0.023), и это не
    экзотика стенда - тот же класс дают живые релизы (старые YIFY без списка правок).
    """
    mkv = tmp_path / "src.mkv"
    mp4 = tmp_path / "late.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate={CLIP_RATE}",
         "-f", "lavfi", "-i", "sine=frequency=440", "-t", "30",
         "-c:v", "libx264", "-preset", "ultrafast", "-g", "50", "-bf", "3",
         "-c:a", "aac", "-y", str(mkv)],
        check=True, capture_output=True,
    )  # fmt: skip
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(mkv),
         "-c", "copy", "-movflags", "+faststart", "-y", str(mp4)],
        check=True, capture_output=True,
    )  # fmt: skip
    return str(mp4)


def test_a_file_that_did_not_open_leaves_the_boundary_as_it_was() -> None:
    """Не вышло - считаем, что встали ровно на границе: врать про место нечем."""
    assert _pilot_start("http://нет-такого.invalid/поток", 12.5, timeout=5.0) == 12.5
    assert _film_start("http://нет-такого.invalid/поток", timeout=5.0) == 0.0


@pytest.mark.ffmpeg
def test_a_container_that_starts_from_zero_needs_no_translation(clip: str) -> None:
    """У mkv и mp4 видео начинается с нуля: сдвиг нулевой и ответ не меняется ни на миллисекунду."""
    assert _film_start(clip) == 0.0
    assert _pilot_start(clip, 41.0) == pytest.approx(40.0, abs=0.5), "докатка mkv потеряна"


@pytest.mark.ffmpeg
def test_the_shift_of_the_whole_container_is_subtracted(clip_shifted: str) -> None:
    """🔴 TC-629. ``-ss`` считается от начала контейнера, а ``-copyts`` печатает метку с ним.

    Замер на стенде: контейнер, чьё видео начинается с 600.006, на ``-ss 40.000`` отвечает
    640.006 - и это число ехало в резы как «где встал прогон», уводя весь список в минус.
    """
    assert _film_start(clip_shifted) == pytest.approx(SHIFT, abs=1.0)
    assert _pilot_start(clip_shifted, 41.0) == pytest.approx(42.0, abs=0.5)


@pytest.mark.ffmpeg
def test_an_mp4_whose_video_starts_late_keeps_the_container_tape(
    clip_mp4_late_start: str,
) -> None:
    """🔴 TC-699. У mp4 карта, сетка, ``-ss`` и ``-copyts`` живут в метках контейнера -
    вычитание ``start_time`` разводит прогон с картой ровно на него (замер: 0.023 на
    всех 20 местах ремукса), и сверка в :data:`SPLIT_SLACK` не сходится никогда.
    """
    raw = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=start_time", "-of", "csv=p=0", clip_mp4_late_start],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    start = float(raw.stdout.strip().splitlines()[0])
    assert start > 0.005, f"фикстура перестала быть своим классом: start_time {start}"
    assert _film_start(clip_mp4_late_start) == 0.0
    # Опорные кадры стоят на ``k * CLIP_KEY_SECONDS + start``. Целимся посередине между
    # двумя из них - так посадка не зависит от того, куда именно легли кадры, - и ждём
    # метку КОНТЕЙНЕРА: кадр плюс ``start``, а не «лента фильма» с вычтенными 0.023.
    key = 10 * CLIP_KEY_SECONDS
    assert _pilot_start(clip_mp4_late_start, key + CLIP_KEY_SECONDS / 2) == pytest.approx(
        key + start, abs=0.01
    )


@pytest.mark.ffmpeg
def test_the_start_of_the_film_is_measured_once_per_file(clip: str) -> None:
    """ffprobe тут стоит десятые доли секунды локально и секунды на живой раздаче,
    а заходов на фильм много: число считается раз и помнится.
    """
    _film_start(clip)
    assert _FILM_START[clip] == 0.0
    _FILM_START[clip] = 3.5  # второй раз ffprobe не зовут
    assert _film_start(clip) == 3.5


def test_an_mp4_named_by_the_map_is_not_asked_of_the_swarm() -> None:
    """У mp4 ответ назначен нулём, поэтому ffprobe живой раздачи не поднимается ни разу.

    Замер, ради которого правило написано (живая раздача, холодный рой, заход с
    2160-й секунды, три прогона): 0.331, 0.172 и 0.122 с — целый процесс, который
    открывает вход и читает голову файла ради числа, известного заранее.
    """
    started: list[list[str]] = []

    def run(command: list[str], **rest: object) -> None:
        started.append(command)
        raise AssertionError("живую раздачу спрашивать не о чем")

    assert _film_start("поток", kind_of=lambda _: "mp4", run=run) == 0.0
    assert started == [], "у названного картой mp4 поднялся лишний процесс"


def test_a_container_the_map_does_not_know_is_still_asked() -> None:
    """Карты нет или контейнер чужой - работает прежний ffprobe, а не выдуманный ноль."""
    started: list[list[str]] = []

    def run(command: list[str], **rest: object) -> None:
        started.append(command)
        raise OSError("ffprobe не поднялся")

    assert _film_start("поток", kind_of=lambda _: "", run=run) == 0.0
    assert len(started) == 1, "чужой контейнер остался без замера"


@pytest.mark.ffmpeg
def test_a_container_without_stamps_is_named_instead_of_answered_silently(
    clip_avi_bframes: str, clip_avi: str, tape: Tape
) -> None:
    """🔴 Мера этой правки: место не измерено - и это СКАЗАНО, а не отдано числом границы.

    Ответ прежний и остаётся прежним: измерителя у этого места нет, подменить его тут
    нечем. Ново ровно одно - событие названо. Замер на стенде (.avi h264 с B-кадрами,
    длительность 300 с, сетка 10 с): пробный прогон не дал первого пакета ни на одной из
    29 границ, настоящая посадка отстоит от границы до 2.035 с, и следом события в
    журнале была пустота.

    Отрицательная проба стоит рядом и той же командой: тот же .avi без B-кадров. Там
    ``pts`` есть, прогон меряет место как на всяком здоровом файле, и ни строки отказа
    появиться не должно - иначе признак записывал бы в слепые исправный вход.
    """
    at = 3 * CLIP_KEY_SECONDS
    blind = _pilot_start(clip_avi_bframes, at)
    assert blind == at, "ответ пробного прогона изменился - это уже другая правка"
    said = [facts for name, facts in tape.calls if name == "пробный прогон не дал первого пакета"]
    assert said, "место не измерено, а в журнале ни строки"
    assert "must be set" in said[0]["отказ"], f"названа не та причина: {said[0]['отказ']}"

    tape.calls.clear()
    seen = _pilot_start(clip_avi, at)
    assert seen < at, f"на входе без B-кадров место обязано измеряться, а не отдаваться: {seen}"
    assert not [name for name, _ in tape.calls if name == "пробный прогон не дал первого пакета"]
