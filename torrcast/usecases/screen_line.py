"""Строка «экран: место из длительности · состояние»: собирает её показ, читает её CLI.

Печатает её сам показ раз в :data:`torrcast.domain.start_settings.SAY_SECONDS`
(:func:`torrcast.usecases.revive_playback._screen._report`), а читает её CLI
(:func:`torrcast.usecases.still_playing.still_playing`) через журнал юнита
(:func:`torrcast.adapters.systemd.unit_why.unit_why`). Другого окна в идущий показ у CLI
нет и быть не может: сендер к приёмнику ровно один, и живёт он внутри юнита.

🔴 Сборка строки вынесена из печати нарочно, и рядом с ней живёт разбор
(:mod:`torrcast.usecases.still_playing`). Разъедься они - переименование в печати оставило
бы разбор молча слепым, и ограждение, которое не даёт погасить живой показ, отвечало бы
«картинки не вижу» ровно там, где картинка есть.
"""

from __future__ import annotations

from torrcast.domain._hms import _hms
from torrcast.domain.catalogs.phrase import phrase


def screen_line(session_tag: str, pos: float, dur: float, state: str) -> str:
    """Строка о состоянии показа - ровно та, что уходит в журнал юнита."""
    return phrase("screen.line", tag=session_tag, pos=_hms(pos), dur=_hms(dur), state=state)
