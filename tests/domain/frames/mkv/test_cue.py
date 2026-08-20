"""Зеркало :mod:`torrcast.domain.frames.mkv.cue`: точка индекса со своим местом в кластере.

Мера про границу: наружу из точки уезжает опорный кадр и ничего кроме, а адрес блока
внутри кластера остаётся внутри разбора матрёшки - рой такими адресами не греется.
"""

from __future__ import annotations

from torrcast.domain.frames.keymap.point import Point
from torrcast.domain.frames.mkv.cue import Cue


def test_a_cue_carries_the_key_frame_and_the_place_of_its_block() -> None:
    """Точка - это опорный кадр плюс смещение названного блока от начала данных кластера."""
    cue = Cue(Point(1.5, 2048, 3), 42)

    assert (cue.point, cue.inside) == (Point(1.5, 2048, 3), 42)


def test_a_muxer_that_named_no_place_leaves_a_zero() -> None:
    """Ноль - «места муксер не назвал»: настоящим смещением ноль быть не может.

    В начале данных кластера стоит ``Timestamp``, поэтому любой блок лежит дальше нуля, и
    спутать «не сказал» с «блок в самом начале» не выйдет.
    """
    assert Cue(Point(0.0, 1024, 1), 0).inside == 0
