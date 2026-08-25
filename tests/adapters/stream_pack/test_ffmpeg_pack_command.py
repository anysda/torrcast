"""Проверяет команду упаковщика: резы от первого пакета, метки фильма и звук для приёмника."""

from __future__ import annotations

import dataclasses

from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.domain.hls_settings import (
    AUDIO_BITRATE,
    AUDIO_CHANNELS,
    AUDIO_CODEC,
    PACK_LIST,
    SPLIT_SLACK,
)
from torrcast.domain.segment_container import FMP4

GRID = Grid.uniform(60.0, 8.0)


def test_fmp4_keeps_explicit_grid_and_makes_every_piece_self_sufficient() -> None:
    """Заголовок едет В КАЖДОМ куске: у показа два кодировщика и два набора параметров.

    Общий заголовок на весь показ приёмник применял и к перекоду - к кадрам, которые им
    не описаны: 334 строки ошибок картинки копией и 1514 полным декодированием против
    нуля со своим заголовком.
    """
    command = ffmpeg_pack_command("вход", 0, "/пак", GRID, 0, 0.0, container=FMP4, video_tag="hvc1")

    assert _cuts(command) == [8.0, 16.0, 24.0, 32.0, 40.0, 48.0]
    assert command[command.index("-segment_format") + 1] == "mp4"
    assert command[command.index("-individual_header_trailer") + 1] == "1"
    assert "-segment_header_filename" not in command, "общего заголовка больше нет"
    assert command[command.index("-segment_format_options") + 1] == "movflags=cmaf"
    assert command[command.index("-tag:v") + 1] == "hvc1"
    assert command[-1] == "/пак/v%d.m4s"


def _cuts(command: list[str]) -> list[float]:
    return [float(x) for x in command[command.index("-segment_times") + 1].split(",")]


def test_the_cuts_are_measured_from_the_first_packet_of_the_run() -> None:
    """Муксер сравнивает метки с начала прогона, а не с начала фильма: резы считаются от ``at``.

    Ровно этот список кладёт границы туда, где они стоят в манифесте, - иначе имя куска
    врало бы о его содержимом.
    """
    command = ffmpeg_pack_command("вход", 0, "/пак", GRID, 2, 14.0)
    assert _cuts(command) == [2.0, 10.0, 18.0, 26.0, 34.0]
    assert command[command.index("-segment_start_number") + 1] == "1", (
        "прогон начался раньше границы - докатка обязана уехать своим куском"
    )


def test_a_run_standing_on_its_boundary_starts_from_its_own_slot() -> None:
    """Докатки нет - и лишнего куска с чужим номером тоже."""
    command = ffmpeg_pack_command("вход", 0, "/пак", GRID, 2, 16.0)
    assert command[command.index("-segment_start_number") + 1] == "2"
    assert _cuts(command) == [8.0, 16.0, 24.0, 32.0]


def test_the_timestamps_stay_the_time_of_the_film() -> None:
    """Без ``-copyts`` ffmpeg сбрасывает метки в ноль на каждом ``-ss``, и приёмник показывал
    бы позицию от начала куска. А одного ``-copyts`` мало: mpegts двигает всё на 1.4 с.
    """
    command = ffmpeg_pack_command("вход", 0, "/пак", GRID, 2, 16.0)
    assert "-copyts" in command
    assert command[command.index("-muxdelay") + 1] == "0"
    assert command[command.index("-muxpreload") + 1] == "0"
    assert command[command.index("-avoid_negative_ts") + 1] == "disabled"
    assert command[command.index("-segment_time_delta") + 1] == f"{SPLIT_SLACK:g}", (
        "допуск реза не тот, по которому сетка решает, встал ли прогон на своей границе"
    )


def test_the_origin_of_the_tape_travels_with_every_run() -> None:
    """🔴 Сдвиг ленты стоит в команде, а не в резах: резы муксер меряет от первого пакета."""
    lifted = dataclasses.replace(GRID, origin=0.083)
    command = ffmpeg_pack_command("вход", 0, "/пак", lifted, 2, 16.0)
    assert command[command.index("-output_ts_offset") + 1] == "0.083"
    assert _cuts(command) == _cuts(ffmpeg_pack_command("вход", 0, "/пак", GRID, 2, 16.0))
    assert "-output_ts_offset" not in ffmpeg_pack_command("вход", 0, "/пак", GRID, 2, 16.0)


def test_the_sound_is_always_the_one_the_receiver_takes() -> None:
    """Приёмнику отдавать AC3 5.1 нельзя: звук всегда наш AAC stereo."""
    command = ffmpeg_pack_command("вход", 3, "/пак", GRID, 0, 0.0)
    assert command[command.index("-c:a") + 1] == AUDIO_CODEC
    assert command[command.index("-ac") + 1] == str(AUDIO_CHANNELS)
    assert command[command.index("-b:a") + 1] == AUDIO_BITRATE
    assert "0:a:3" in command, "дорожка выбирается человеком, а не первой попавшейся"
    assert command[command.index("-segment_list") + 1] == f"/пак/{PACK_LIST}"
    assert command[-1] == "/пак/v%d.ts"


def test_a_grid_on_keyframes_never_cuts_inside_a_gop() -> None:
    """На сетке по опорным кадрам муксер сам дождётся кадра; на ровной - наоборот."""
    keyed = Grid.on_keyframes([0.0, 9.0, 21.0, 30.0, 45.0], 60.0, 10.0)
    command = ffmpeg_pack_command("вход", 0, "/пак", keyed, 0, 0.0)
    assert command[command.index("-break_non_keyframes") + 1] == "0"
    plain = ffmpeg_pack_command("вход", 0, "/пак", GRID, 0, 0.0)
    assert plain[plain.index("-break_non_keyframes") + 1] == "1"


def test_the_arguments_are_a_list_and_a_path_with_a_space_survives() -> None:
    """⚠️ Разбиение по пробелам разрывало надвое любой путь с пробелом, и список нарезки
    не появлялся вовсе: наружу не выкладывалось ничего, а показ видел «ни куска».
    """
    command = ffmpeg_pack_command("вход", 0, "/пак с пробелом", GRID, 0, 0.0)
    assert f"/пак с пробелом/{PACK_LIST}" in command
    assert all(isinstance(item, str) for item in command)


def test_an_encoder_run_is_limited_to_its_own_stretch() -> None:
    """Кодировщик работает заходами по несколько кусков, чтобы перемотка успевала вмешаться."""
    command = ffmpeg_pack_command("вход", 0, "/пак", GRID, 0, 0.0, until=2)
    assert command[command.index("-to") + 1] == f"{GRID.end(2) + 1.0:.3f}"
    assert _cuts(command) == [8.0, 16.0, 24.0], "заход обещает больше кусков, чем ему велено"
