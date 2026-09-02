"""Запись показа: всё, что юнит и ``cast status`` узнают о выбранном файле.

Собирает её команда показа (:func:`_cmd_play`) один раз, из паспорта ffprobe.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.entry import Entry
from torrcast.domain.estimated_video_mbit import estimated_video_mbit
from torrcast.domain.media import Media
from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify
from torrcast.domain.studio import Studio
from torrcast.domain.torr_file import TorrFile
from torrcast.domain.track_studio import track_studio
from torrcast.usecases.select._prep import _Prep

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
    seen: str,
    args: Args,
) -> Entry:
    """Запись показа по выбранному релизу: паспорт, дорожка, серия и список серий.

    ``seen`` - студия, которой эту картину уже смотрели (:func:`_studio_seen`): память
    картины, а не факт этого запуска, и переписывать её вынужденным дефолтом нельзя.
    """
    series = plan.series
    played = _named(track_studio(prep.voiced, audio, release.studios))
    # Явный выбор человека - единственное, что вправе назначить картине другую студию:
    # `--voice N` и меню озвучек называют дорожку сами (:func:`pick_voice`).
    studio = played if args.voice is not None else (seen or played)
    # Список серий берётся у ТОЙ раздачи, которую играем, и разбирается здесь заново:
    # подготовка спрашивает соседние раздачи параллельно, и общего места, где список
    # мог бы полежать, у них нет (:meth:`torrcast.domain._series._Series.choose`).
    episodes = series.table(prep.files, release.season) if series else []
    # 🔴 TC-807. Сезон и серия пишутся по ТОМУ файлу, который играет, а не по запросу:
    # запрос мог звать «s1e1» серию, которая в этой раздаче - s5e1, и подпись на экране
    # обязана совпадать с записью. Файл вне таблицы серий (ручка ``--file N``) - серии
    # у показа нет, и выдумывать её из запроса - та же ложь.
    placed = next((row for row in episodes if row[2] == video.index), None)
    measured_mbit = media.video_bps / 1e6
    estimated_mbit = estimated_video_mbit(video.size, media.duration)
    return Entry(
        title=plan.picture.title,
        magnet=release.magnet,
        year=plan.picture.year or 0,
        # Оригинальное имя - рядом с записанным: под EN показ зовёт картину им, и снимок
        # сессии обязан назвать её так же, как назвала строка запуска.
        original=plan.picture.original or "",
        kind="tv" if plan.picture.kind == "tv" else "movie",
        file_idx=video.index,
        audio=audio,
        # Дорожка едет из отдельного файла, а какого именно - показ спрашивает у
        # раздачи тем же правилом (:func:`torrcast.domain.voice_beside.voice_beside`):
        # у каждой серии свой файл звука, а список серий про него не знает.
        voiced_apart=prep.apart,
        voice=voice,
        # Чья это озвучка - спрашивается у дорожки и у имени раздачи: следующий сезон
        # будет другим релизом, и одна эта строка - всё, чем он узнает, чем сериал
        # смотрели (:func:`track_studio`).
        studio=studio,
        # А это уже не память, а факт: запомненной студии в релизе не нашлось, играет
        # другая, и зритель прочтёт об этом на экране (:func:`voice_swap`).
        heard=played if played and played != studio else "",
        dur=media.duration,
        # Паспортный вес точнее; если его нет, верхняя оценка по размеру выбранного
        # файла и длительности всё равно даёт профилю цели с первой секунды.
        vbps=measured_mbit or estimated_mbit or -1.0,
        vbps_estimated=not measured_mbit and bool(estimated_mbit),
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
        season=placed[0] if placed else None,
        episode=placed[1] if placed else None,
        episodes=episodes,
    )


def _named(studio: Studio | None) -> str:
    """Имя студии для памяти картины; не узнали - пусто."""
    return studio.name if studio is not None else ""
