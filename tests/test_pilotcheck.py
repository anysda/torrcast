"""Щуп сверки меряет ответ настоящего пробного прогона, а не свою копию его."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from tests.conftest import CLIP_SECONDS
from torrcast.domain.hls_settings import HLS_SEGMENT_SECONDS

SPEC = importlib.util.spec_from_file_location(
    "pilotcheck", Path(__file__).resolve().parent.parent / "scripts/pilotcheck.py"
)
assert SPEC is not None and SPEC.loader is not None
check = importlib.util.module_from_spec(SPEC)
sys.modules["pilotcheck"] = check
SPEC.loader.exec_module(check)


def _row(at: float, told: float, stood: float | None, plain: float | None) -> object:
    """Одна строка замера; исход считается тем же правилом, что и в живом прогоне."""
    kind = check.APART
    if stood is not None and abs(told - stood) <= 0.02:
        kind = check.AGREED
    elif abs(told - at) <= 0.02:
        kind = check.VERBATIM
    return check.Row(at, told, stood, plain, "", kind)


def test_the_check_goes_red_when_the_second_way_disagrees_with_the_live_run() -> None:
    """🔴 Отрицательная проба поверки: разъехались способы - и это сказано числом.

    Без этого «поверено» ничего не стоит: колонка, которая не умеет покраснеть, зеленела
    бы и на способе, который меряет не то место. Живой пример такого способа известен:
    перемотка ВЫХОДА вместо входа (``-ss`` после ``-i``) на том же ролике отвечает 0.100
    там, где боевой прогон садится на 97.932, - поверка обязана назвать это разъездом.
    """
    apart = [_row(100.0, 97.9, 0.1, 97.932), _row(110.0, 108.3, 0.2, 108.359)]
    said = check.summary(apart, 0.0)
    assert said["поверка разошлась"] == 2
    assert said["поверено"] == 0

    together = [_row(100.0, 97.932, 97.932, 97.932), _row(110.0, 108.359, 108.359, 108.359)]
    assert check.summary(together, 0.0)["поверка разошлась"] == 0


def test_a_boundary_answered_verbatim_is_told_apart_from_a_measured_one() -> None:
    """«Встали ровно на границе» и «не измерили ничего» приходят одним числом - и разводятся.

    Разводит их второй способ: он назвал место, и место это не граница. Не будь его,
    обе строки читались бы как удачный замер.
    """
    rows = [_row(100.0, 100.0, 97.972, None), _row(110.0, 108.359, 108.359, 108.359)]
    said = check.summary(rows, 0.0)
    assert said[check.VERBATIM] == 1
    assert said[check.AGREED] == 1
    assert said["наибольшее расхождение"] == pytest.approx(2.028, abs=0.001)


def test_the_widest_gap_is_counted_only_where_something_was_measured() -> None:
    """Неизмеренная граница не даёт ни нуля, ни расхождения: её просто нет в счёте."""
    said = check.summary([_row(100.0, 100.0, None, None)], 0.0)
    assert said["измерено вторым способом"] == 0
    assert said["наибольшее расхождение"] == 0.0


@pytest.mark.ffmpeg
def test_the_pilot_is_blind_on_a_container_without_stamps_and_the_check_says_by_how_much(
    clip_avi_bframes: str, clip_avi: str
) -> None:
    """🔴 Мера щупа настоящим ffmpeg: на .avi с B-кадрами продукт отвечает границей всегда.

    Границы берутся сеткой показа, а шаг опорных кадров ролика (``CLIP_GOP``/``CLIP_FPS``
    = 2.085 с) её не делит - иначе посадка ложилась бы на границу сама, и слепота прогона
    ничем бы не отличалась от правды.

    Отрицательная проба той же командой - тот же .avi без B-кадров: там боевой прогон
    меряет место сам, и щуп обязан совпасть с ним знак в знак. Зеленей щуп на обоих
    входах - он мерил бы не тот класс.
    """
    walls = check.boundaries(CLIP_SECONDS, HLS_SEGMENT_SECONDS)
    blind = [check.check(clip_avi_bframes, at, 30.0, 0.0) for at in walls]
    said = check.summary(blind, 0.0)
    assert said[check.VERBATIM] == len(walls), f"слепота прогона не на всех границах: {said}"
    assert said["боевой прогон дал пакет"] == 0, "mpegts принял поток без меток - класс не тот"
    assert said["измерено вторым способом"] == len(walls), "второй способ тоже ничего не намерил"
    assert said["наибольшее расхождение"] > 0.0, "посадка совпала с границей на всех местах"
    assert all(row.stood is not None and row.stood < row.at for row in blind), (
        "на .avi перемотка садится РАНЬШЕ границы, и замер обязан это показывать"
    )

    seen = [check.check(clip_avi, at, 30.0, 0.0) for at in walls]
    healthy = check.summary(seen, 0.0)
    assert healthy["поверено"] == len(walls), f"поверка разошлась на исправном входе: {healthy}"
    assert healthy[check.AGREED] == len(walls), "щуп разошёлся с прогоном там, где тот меряет сам"
