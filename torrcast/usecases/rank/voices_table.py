"""Список озвучек с пометками; зовут меню озвучек и `cast voices`."""

from __future__ import annotations

from torrcast.domain.media import Media


def voices_table(media: Media, default: int, remembered: str = "") -> str:
    """Список озвучек с пометками «дефолт» и «запомнено» — для меню и ``cast voices``."""
    found = media.find_voice(remembered) if remembered else None
    rows = []
    for track in media.tracks:
        marks = (("дефолт", track.index == default), ("запомнено", track.index == found))
        note = [word for word, on in marks if on]
        tail = f"   [{', '.join(note)}]" if note else ""
        rows.append(f"  {track.index + 1}. {track.label}{tail}")
    return "\n".join(["Озвучка:", *rows])
