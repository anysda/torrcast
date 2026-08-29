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

#: Слово, которым строка ИДУЩЕГО показа отличается от строки темноты.
SCREEN = "экран"


def screen_line(session_tag: str, pos: float, dur: float, state: str) -> str:
    """Строка о состоянии показа - ровно та, что уходит в журнал юнита."""
    return f"{session_tag} {SCREEN}: {_hms(pos)} из {_hms(dur)} · {state}"
