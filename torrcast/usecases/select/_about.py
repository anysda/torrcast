"""Строка показа по записи состояния: картина, серия, качество, дорожка и место."""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.domain.voice_swap import voice_swap
from torrcast.usecases.rank._hms import _hms

#: Ручка, которой зритель просит меню картин вместо записанного выбора. Строку читают
#: ровно там, где играет закладка, поэтому имя ручки стоит в ней самой: искать его в
#: справке человеку неоткуда - он не спрашивал.
_OTHER = "выбрать другое: --menu"


def _about(entry: Entry) -> str:
    """Строка показа по записи состояния: «Киберпанк» · s1e2 · дорожка 1 · с 0:03:20.

    Студия называется отдельным словом, если подпись дорожки о ней молчит: у сезонной
    раздачи подпись это голое ``rus``, и по ней человек не отличит студию, которой он
    смотрит сериал, от любой другой (:attr:`torrcast.domain.entry.Entry.studio`). Называется
    при этом ТА, ЧТО ИГРАЕТ: запомненной студии в релизе может не быть вовсе, и тогда
    строка говорит и что играет, и вместо чего (:func:`voice_swap`).

    Последним словом строка называет ручку, которой поднимают меню картин
    (:attr:`torrcast.domain.args.Args.menu`): играет тут записанный выбор, и другого
    места сказать о выборе нет.
    """
    voice = entry.voice or f"дорожка {entry.audio + 1}"
    studio = entry.heard or entry.studio
    if studio and studio.casefold() not in voice.casefold():
        voice = f"{voice} ({studio})"
    parts = [f"«{entry.title}»", entry.label, entry.quality, voice]
    parts.append(voice_swap(entry.studio, entry.heard))
    if entry.pos > 0:
        parts.append(f"с {_hms(entry.pos)}")
    parts.append(_OTHER)
    return " · ".join(filter(None, parts))
