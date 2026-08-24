"""Имя файла сегмента по его месту в фильме.

Зовут его упаковка, выкладка наружу и кодировщик тяжёлых кусков."""

from __future__ import annotations

from torrcast.domain.segment_container import MPEGTS, SegmentContainer
from torrcast.domain.segment_suffix import segment_suffix


def segment_name(slot: int, container: SegmentContainer = MPEGTS) -> str:
    """Имя файла сегмента. Имя = место в фильме, а не номер по порядку упаковки — это и
    делает возможным манифест на весь фильм при упаковке по требованию.
    """
    return f"v{slot}{segment_suffix(container)}"
