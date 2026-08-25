"""Имя склеенного куска внутри каталога прогона.

Спрашивают его выкладка (:mod:`torrcast.adapters.stream_pack.packer_publish`) и ужатие на
месте (:mod:`torrcast.adapters.stream_pack._shrunk_out`).
"""

from torrcast.domain.hls_settings import MIXED_PREFIX
from torrcast.domain.segment_container import SegmentContainer
from torrcast.domain.segment_suffix import segment_suffix


def mixed_name(slot: int, container: SegmentContainer) -> str:
    """Как зовётся склейка этого места: приставка, слот и расширение контейнера.

    🔴 Расширение тут не украшение, а выбор муксера: по нему ffmpeg решает, чем писать
    склейку, а выкладка отдаёт получившийся файл приёмнику под именем куска. Пока имя
    было прибито к ``.ts``, склейка на fMP4 собиралась чужим муксером, не выходила и
    оставляла место без единого выложенного куска.
    """
    return f"{MIXED_PREFIX}{slot}{segment_suffix(container)}"
