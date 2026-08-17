"""Пороги перекода: замеренные числа и порядок звеньев в цепочке HDR→SDR."""

from __future__ import annotations

from torrcast.adapters.recode.encode_settings import (
    _KEY_SLACK,
    FIT_FLOOR,
    FIT_SLACK,
    MAXRATE_GAIN,
    TONEMAP,
    VBV_SECONDS,
)


def test_the_measured_thresholds_keep_their_numbers() -> None:
    """Каждое из этих чисел куплено разбором живого показа, а не выбрано на глаз."""
    assert MAXRATE_GAIN == 1.08, "потолок выше цели на 8 %: ниже кап душит движение"
    assert VBV_SECONDS == 0.5, "буфер VBV в полсекунды держит худшую секунду в 10-13 Мбит"
    assert FIT_SLACK == 0.9, "замер живого показа: сегмент выходит до 21 % выше предсказанного"
    assert FIT_FLOOR == 1.0, "ниже этого смотреть нельзя, честнее пропустить место"
    assert _KEY_SLACK == 0.02, "опорный кадр просится раньше границы на допуск муксера"


def test_the_buffer_is_shorter_than_the_two_seconds_that_killed_the_start() -> None:
    """Прежний буфер был «две секунды цели» - на нём первый кусок уходил в 25 Мбит."""
    assert VBV_SECONDS * MAXRATE_GAIN < 2.0


def test_the_colour_chain_converts_before_it_relabels() -> None:
    """Метка без преобразования - переклеенный ярлык, и порядок звеньев тут и есть смысл.

    Сперва PQ разворачивается в линейный свет, потом тонемап, и только потом кадр
    собирается в BT.709.
    """
    steps = TONEMAP.split(",")
    assert steps[0] == "zscale=t=linear:npl=100", "сперва линейный свет и яркость экрана"
    assert steps[1] == "tonemap=tonemap=hable:desat=0", "кривая hable и без обесцвечивания"
    assert steps[2].startswith("zscale=t=bt709"), "сборка обратно в BT.709 идёт после тонемапа"
    assert steps[-1] == "format=yuv420p"
    assert TONEMAP.index("tonemap=") < TONEMAP.index("t=bt709"), "ярлык после преобразования"
