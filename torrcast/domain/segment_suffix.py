"""Расширение сегмента выбранного контейнера."""

from torrcast.domain.segment_container import FMP4, SegmentContainer


def segment_suffix(container: SegmentContainer) -> str:
    """Назвать расширение куска выбранного контейнера."""
    return ".m4s" if container == FMP4 else ".ts"
