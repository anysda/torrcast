"""Запись показа: всё, что юнит и ``cast status`` узнают о выбранном файле.

Собирает её команда показа (:func:`_cmd_play`) один раз, из паспорта ffprobe.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.entry import Entry
from torrcast.domain.media import Media
from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.select import _Prep

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.usecases.select.plan import Plan


def _entry_for(
    plan: Plan,
    prep: _Prep,
    release: Release,
    video: TorrFile,
    media: Media,
    audio: int,
    voice: str,
    args: Args,
) -> Entry:
    """Запись показа по выбранному релизу: паспорт, дорожка, серия и список серий."""
    series = plan.series
    return Entry(
        title=plan.picture.title,
        magnet=release.magnet,
        kind="tv" if plan.picture.kind == "tv" else "movie",
        file_idx=video.index,
        audio=audio,
        voice=voice,
        dur=media.duration,
        # Вес видеодорожки из паспорта: по нему показ строит профиль тяжести с первой
        # секунды, не набирая поправку «контейнер → ТВ» вслепую.
        vbps=media.video_bps / 1e6 or -1.0,
        # Кодек оттуда же: по нему показ решает, играть копией или перекодировать файл
        # целиком, и решает это один раз - до первого сегмента (:func:`_encode_all`).
        codec=media.video or "",
        # И глубина цвета рядом: одного имени кодека для этого решения не хватает.
        depth=media.depth,
        # То, что уехало на ТВ: `cast status` покажет факт, а не заявку имени.
        quality=media.quality if media.height else "",
        # Тот же кадр числом: по нему показ решает, до чего ужать картинку перекодом.
        frame=media.frame,
        # И HDR оттуда же: ужатому кадру ещё решать, приводить ли цвет к SDR.
        hdr=media.hdr,
        query=slugify(args.title_query),
        season=series.want.season if series else None,
        episode=series.want.episode if series else None,
        # Список серий берётся у ТОЙ раздачи, которую играем, и разбирается здесь заново:
        # подготовка спрашивает соседние раздачи параллельно, и общего места, где список
        # мог бы полежать, у них нет (:meth:`torrcast.domain._series._Series.choose`).
        episodes=series.table(prep.files, release.season) if series else [],
    )
