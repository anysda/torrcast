"""Место показа для записи: показанный кадр, а пока ТВ ищет место перемотки - её цель.

Закладка держит показанный кадр (:attr:`_Screen.held`), и ``BUFFERING`` в неё не идёт:
сторож подвиса гонит указатель вперёд по 8 с. Но перемотку с пульта ТВ показ узнаёт только
от приёмника, и до первого кадра на новом месте запись стояла на старом. Стенд 06-10-2026,
«Play on TV» с карточки, пульт «+600» со 119.9: ТВ 14 с в буфере на 719.9, а карточка шла
часами от 113.7. Перемотку от подвиса отличает скачок между двумя опросами: шаг сторожа
8 с, а дальше :data:`torrcast.usecases.watch.SEEK_SECONDS` указатель сам не прыгает.
"""

from __future__ import annotations

from torrcast.domain.position import Position
from torrcast.usecases.revive_playback._screen_state import _Screen
from torrcast.usecases.watch import SEEK_SECONDS


def _landing(screen: _Screen, position: Position) -> float:
    """Место для записи; цель перемотки держится, пока ТВ не заиграл."""
    was, screen.tv_was = screen.tv_was, position.pos
    if position.state != "BUFFERING":
        screen.aim = -1.0
    elif was >= 0.0 and abs(position.pos - was) > SEEK_SECONDS:
        screen.aim = position.pos
    return screen.held if screen.aim < 0.0 else screen.aim
