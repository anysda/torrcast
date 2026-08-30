"""Список озвучек с пометками; зовут меню озвучек и `cast voices`."""

from __future__ import annotations

from collections.abc import Sequence

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.media import Media
from torrcast.domain.studio import Studio
from torrcast.domain.track_studio import track_studio


def voices_table(
    media: Media, default: int, remembered: str = "", studios: Sequence[Studio] = ()
) -> str:
    """Список озвучек с пометками «дефолт» и «запомнено» — для меню и ``cast voices``."""
    found = media.find_voice(remembered) if remembered else None
    rows = []
    for track in media.tracks:
        marks = (
            (phrase("rank.default_mark"), track.index == default),
            (phrase("rank.remembered_mark"), track.index == found),
        )
        note = [word for word, on in marks if on]
        tail = f"   [{', '.join(note)}]" if note else ""
        studio = track_studio(media, track.index, studios)
        named = f" ({studio.name})" if studio is not None else ""
        if studio is not None and studio.name.casefold() in track.label.casefold():
            named = ""
        rows.append(f"  {track.index + 1}. {track.label}{named}{tail}")
    return "\n".join([phrase("rank.voices_header"), *rows])
