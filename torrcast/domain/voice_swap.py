"""Честная строка про вынужденную подмену озвучки; зовут её подписи показа."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase


def voice_swap(studio: str, heard: str) -> str:
    """Подмена озвучки одной строкой; пусто - подмены нет.

    Запомненной студии в новом релизе может не быть вовсе - на границе сезона это
    обычное дело, - и тогда играется та, что есть
    (:func:`torrcast.usecases.rank.pick_voice.pick_voice`). Молчать об этом нельзя: зритель
    слышит другой дубляж и не знает, чем это объяснить.

    Одинаковые имена подменой не считаются: студию называют и дорожка, и имя раздачи, и
    регистр у них разный.
    """
    if not heard or not studio or heard.casefold() == studio.casefold():
        return ""
    return phrase("stream.voice_swap", heard=heard, studio=studio)


__all__ = ["voice_swap"]
