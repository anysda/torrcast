"""Зеркало :mod:`torrcast.domain.recode_settings`: что НАША машина успевает в реальном времени.

Число здесь про железо, на котором крутится torrcast, а не про приёмник. Сторожится связь с
замером: выше этой ступени сплошной перекод идёт вровень с показом, то есть запаса нет
вовсе, а ниже - мы ужимали бы честный HD без нужды.
"""

from __future__ import annotations

from torrcast.adapters.recode import Encode
from torrcast.domain.recode_settings import RECODE_HEIGHT

#: Замер на 4 vCPU: сплошной перекод 2160p БЕЗ ужатия идёт 1.03x реального времени, то есть
#: вровень с показом, а тот же перекод со скейлом до 1080p - 1.53x.
UNSCALED_4K_REALTIME = 1.03
SCALED_4K_REALTIME = 1.53


def test_the_ceiling_stays_where_the_encoder_still_has_room_over_realtime() -> None:
    """Потолок стоит на ступени, до которой мы УЖИМАЕМ, а не на той, выше которой не умеем.

    Подними его к росту исходника - и перекод пойдёт вровень с показом (замер: 1.03x), то
    есть без запаса на прогрев, который рядом отнимает своё. Опусти ниже HD - и честный
    720p ужимался бы в SD там, где ужимать нечего.
    """
    assert UNSCALED_4K_REALTIME < SCALED_4K_REALTIME, "скейл - разгрузка, а не лишняя нагрузка"
    assert 720 <= RECODE_HEIGHT < 2160


def test_a_frame_above_the_ceiling_is_shrunk_to_it_and_one_below_is_left_alone() -> None:
    """Число участвует в решении кодировщика, а не лежит рядом с ним.

    Кадр крупнее потолка уезжает ужатым ровно до него и говорит об этом в имени каталога
    прогретого; кадр не крупнее не трогается вовсе - иначе прогретое прошлых показов легло
    бы под другим ключом и не нашлось.
    """
    tall = Encode(preset="ultrafast", mbit=9.0, frame=2160, ceiling=RECODE_HEIGHT)
    assert tall.scaled
    assert tall.out_frame == RECODE_HEIGHT

    fitting = Encode(preset="ultrafast", mbit=9.0, frame=RECODE_HEIGHT, ceiling=RECODE_HEIGHT)
    assert not fitting.scaled
    assert fitting.out_frame == RECODE_HEIGHT
    assert fitting.mark == "", "неужатый кадр не смеет менять ключ прогретого"
