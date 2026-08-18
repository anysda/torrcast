"""Зеркало :mod:`torrcast.domain.delivered_mbit`: во что обходится кусок, уехавший на ТВ.

Цифра эта завоёвана замером и стоит в основании всех решений о тяжести: по ней отбор
бракует релиз, а прогрев считает бюджет диска. Считать «видео как есть» - соврать на
двадцатую часть, и врать эта ошибка будет ровно в ту сторону, где приёмник встаёт.
"""

from __future__ import annotations

import pytest

from torrcast.domain.delivered_mbit import AUDIO_MBIT, TS_OVERHEAD, delivered_mbit


def test_the_wire_carries_more_than_the_video_track() -> None:
    """К дорожке добавляется наш звук и оверхед mpegts, а не только первый или второй."""
    went = delivered_mbit(14_330_000)

    assert went == (14.33 + AUDIO_MBIT) * TS_OVERHEAD
    assert went > 14.33, "уехало больше, чем весила дорожка"


def test_a_silent_passport_is_not_the_same_as_a_light_file() -> None:
    """Паспорт промолчал - считать не по чему, и это ноль-незнание, а не ноль-мегабит.

    Выдай правило прикидку - решение «перекодировать целиком» принималось бы по выдумке.
    """
    assert delivered_mbit(0.0) == 0.0
    assert delivered_mbit(-1.0) == 0.0


def test_the_audio_share_does_not_depend_on_the_source_track() -> None:
    """Звук исходника ни при чём: в сегмент всегда уезжает наш AAC.

    Считай мы дорожку исходника - DTS «Тачек 3» добавил бы полтора лишних мегабита к
    каждому решению о тяжести куска.
    """
    grown = delivered_mbit(2_000_000) - delivered_mbit(1_000_000)

    assert grown == pytest.approx(1.0 * TS_OVERHEAD)
