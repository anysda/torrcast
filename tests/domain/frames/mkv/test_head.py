"""Зеркало :mod:`torrcast.domain.frames.mkv.head`: голова mkv одним разбором.

Мера про то, ради чего голова читается вообще: адрес ``Cues`` в ней отсчитан от начала
данных ``Segment``, а наружу обязан приехать абсолютным. Ошибись разбор тут - индекс
читался бы не с того места файла.
"""

from __future__ import annotations

from tests.domain.frames.mkv.blocks import Matroska
from torrcast.domain.frames.mkv.head import Head


def test_the_head_tells_where_cues_are_and_how_time_is_scaled() -> None:
    """Адрес Cues абсолютный, масштаб и длительность - из ``Info``."""
    data, base = Matroska().bytes()
    facts = Head(data)

    assert facts.segment == base
    assert facts.cues_at is not None and facts.cues_at > base
    assert data[facts.cues_at] == 0x1C, "по адресу обязан лежать сам элемент Cues"
    assert facts.scale == 1_000_000
    assert facts.duration == 6000.0


def test_the_head_names_the_video_track_and_its_codec() -> None:
    """Элемент ``Tracks`` называет дорожку видео сам - гадать по точкам Cues не нужно."""
    data, _base = Matroska().bytes()
    facts = Head(data)

    assert facts.video == 1
    assert facts.codec == "V_MPEG4/ISO/AVC"


def test_a_head_without_tracks_names_no_video_track() -> None:
    """``Tracks`` не прочитался - дорожка не названа, и врать о ней разбор не станет."""
    data, _base = Matroska(forget_tracks=True).bytes()
    facts = Head(data)

    assert facts.video is None
    assert facts.codec == ""


def test_a_seek_head_without_cues_leaves_the_address_empty() -> None:
    """Записи о Cues в SeekHead нет - адреса нет, и врать о нём разбор не станет."""
    data, _base = Matroska(forget_cues=True).bytes()
    facts = Head(data)

    assert facts.segment is not None
    assert facts.cues_at is None


def test_without_a_segment_nothing_is_read() -> None:
    """Это не mkv: ни Segment, ни масштаба - умолчания и пустой адрес."""
    facts = Head(b"\x00" * 32)

    assert facts.segment is None
    assert facts.cues_at is None
    assert facts.duration == 0.0
