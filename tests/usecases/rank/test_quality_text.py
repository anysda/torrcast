"""Печатается подтверждённый кадр; заявка имени говорит, только когда паспорт молчит."""

from __future__ import annotations

from tests.usecases.rank.releases import media, rel
from torrcast.usecases.rank.quality_text import quality_text


def test_the_passport_beats_the_name() -> None:
    """«Моана 2» печаталась 1080p при 1150x574: заявка выигрывала у факта."""
    assert quality_text(rel(quality="1080p"), media(height=574, width=1150)) == "574p"


def test_the_name_speaks_only_when_the_passport_is_silent() -> None:
    assert quality_text(rel(quality="1080p"), media(height=0, width=0)) == "1080p"
    assert quality_text(rel(quality=None), media(height=0, width=0)) == "?"


def test_the_scan_letter_comes_from_the_stream() -> None:
    """Гребёнку нельзя подписать прогрессивом, как бы её ни звало имя раздачи."""
    assert quality_text(rel(quality="1080p"), media(field_order="tt")) == "1080i"
