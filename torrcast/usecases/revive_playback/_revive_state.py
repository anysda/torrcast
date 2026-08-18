"""Внешний мир оживления показа: часы боевого пути и отметка о картинке.

Кладёт их композиционный корень (:mod:`torrcast.runtime.wire`) одним словом
(:func:`_configure_revive_playback`); читают лестница подъёма и держатель показа.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from torrcast.ports.clock import Clock

#: Внешний мир оживления показа. Всё это кладёт композиционный корень
#: (:mod:`torrcast.runtime.wire`): часы боевого пути и флажок картинки - это настоящее
#: время и настоящий файл, а сценарию о них знать нечего. До слова корня оживление
#: обходится теми часами, которые ему подали аргументом.
_revive_clock: Clock
_revive_playing_mark: Callable[[Path], None]

#: Сколько терпим НЕПОДВИЖНЫЙ указатель за долей длительности, прежде чем считать сеанс
#: доигранным (:func:`_hold`). Страховка перехода: конец потока приёмник называет не
#: всегда, а переход дороже хвоста.
TAIL_LIMIT = 60.0


def _configure_revive_playback(clock: Clock, playing_mark: Callable[[Path], None]) -> None:
    """Назначить оживлению показа его внешний мир: часы и отметку о картинке."""
    global _revive_clock, _revive_playing_mark
    _revive_clock = clock
    _revive_playing_mark = playing_mark
