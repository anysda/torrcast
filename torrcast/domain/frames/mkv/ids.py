"""Идентификаторы элементов EBML и размеры кусков, которыми mkv читается с роя.

Отдельным модулем потому, что их спрашивают все разборщики матрёшки сразу
(:mod:`~torrcast.domain.frames.mkv.head`, :mod:`~torrcast.domain.frames.mkv.keys`), и
держи их любой из них - соседи замкнулись бы друг на друга.
"""

from __future__ import annotations

from typing import Final

#: EBML-идентификаторы, которые нам нужны (вместе с маркером длины, как в файле).
SEGMENT: Final = 0x18538067
SEEK_HEAD: Final = 0x114D9B74
SEEK: Final = 0x4DBB
SEEK_ID: Final = 0x53AB
SEEK_POSITION: Final = 0x53AC
INFO: Final = 0x1549A966
TIMESTAMP_SCALE: Final = 0x2AD7B1
DURATION: Final = 0x4489
CLUSTER: Final = 0x1F43B675
SIMPLE_BLOCK: Final = 0xA3
BLOCK_GROUP: Final = 0xA0
BLOCK: Final = 0xA1
TRACKS: Final = 0x1654AE6B
TRACK_ENTRY: Final = 0xAE
TRACK_NUMBER: Final = 0xD7
TRACK_TYPE: Final = 0x83
CODEC_ID: Final = 0x86
CUES: Final = 0x1C53BB6B
CUE_POINT: Final = 0xBB
CUE_TIME: Final = 0xB3
CUE_TRACK_POSITIONS: Final = 0xB7
CUE_TRACK: Final = 0xF7
CUE_CLUSTER_POSITION: Final = 0xF1
CUE_RELATIVE_POSITION: Final = 0xF0

#: Запасной размер головы: :data:`~torrcast.adapters.frames.keyframes.HEAD_PEEK` не хватило (длинный
#: SeekHead, толстые теги).
HEAD_BYTES: Final = 4 << 20
#: Сколько берём с места Cues одним куском. Тело Cues - сотни килобайт (замерено: 163,
#: 189 и 456 КБ), поэтому оно влезает целиком, и хвост стоит **одного** запроса вместо
#: двух: заголовок и тело раньше читались порознь, а холодный рой платит за каждый заход.
CUES_CHUNK: Final = 1 << 20
