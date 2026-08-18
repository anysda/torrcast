"""Зеркало завода сплошного перекода: настоящий ``whole_encode`` отвечает договору."""

from __future__ import annotations

from torrcast.adapters.recode import whole_encode
from torrcast.ports.recode.encoding import Encoding
from torrcast.usecases.playback.whole_encodings import WholeEncodings


def test_the_real_factory_answers_the_named_contract() -> None:
    """Завод зовут ровно так, как объявлено, и он отдаёт названное решение."""
    named: WholeEncodings = whole_encode

    made: Encoding = named(9.0, video_mbit=20.0, frame=2160, ceiling=1080, hdr=False)

    assert made.mbit > 0.0
    assert made.out_frame == 1080, "4К обязано ужиматься до потолка приёмника"


def test_a_light_source_is_not_blown_up_to_the_ceiling() -> None:
    """Цель считается ОТ ИСТОЧНИКА: лёгкое аниме не раздувается в полные девять."""
    named: WholeEncodings = whole_encode

    assert named(9.0, video_mbit=1.3).mbit < 9.0
