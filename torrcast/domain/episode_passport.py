"""Паспорт файла в записи серии: одним правилом для показа и прогрева следующей серии."""

from __future__ import annotations

from dataclasses import replace

from torrcast.domain.entry import Entry
from torrcast.domain.media import Media
from torrcast.domain.video_weight import video_weight


def episode_passport(entry: Entry, media: Media) -> Entry:
    """Запись серии, в которую лёг паспорт её файла: длительность, вес, кодек, глубина,
    кадр и HDR.

    🔴 Из этих полей сетка и решение о перекоде считаются дважды: показом
    (:func:`torrcast.usecases.playback.entry_layout.entry_layout`) и прогревом следующей серии
    впрок (:func:`torrcast.usecases.playback._next_warmer._next_warmer`). Пока прогрев брал
    вес из голого ffprobe, а показ - из записи с оценкой по размеру, у HEVC без веса в
    паспорте сплошной перекод прогрева шёл на 8.3 Мбит/с, а показа - на 3.0: прогретое
    ложилось под чужим ключом, и первый кусок следующей серии паковался на лету.
    """
    row = next(
        (item for item in entry.episodes if len(item) >= 3 and item[2] == entry.file_idx), []
    )
    vbps, estimated = video_weight(media, row[3] if len(row) >= 4 else 0)
    return replace(
        entry,
        dur=media.duration or entry.dur,
        vbps=vbps,
        vbps_estimated=estimated,
        # Кодек, глубина, кадр и HDR у следующей серии свои: в раздаче аниме нередко
        # лежат и HEVC, и H.264, а Hi10P без глубины неотличим от обычного H.264.
        codec=media.video or "",
        depth=media.depth,
        frame=media.frame,
        hdr=media.hdr,
    )
