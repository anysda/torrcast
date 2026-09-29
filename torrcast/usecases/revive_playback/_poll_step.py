"""Шаг круга опроса приёмника: где учащать, а где хватит обычных двух секунд.

Зовёт его только :func:`torrcast.usecases.revive_playback._hold._hold`.
"""

from __future__ import annotations

from torrcast.domain.position import Position
from torrcast.domain.start_settings import END_POLL_WINDOW, FIRST_FRAME_POLL
from torrcast.usecases.revive_playback._screen_state import _Screen

#: Обычный шаг опроса приёмника, секунды.
POLL_SECONDS = 2.0


def _poll_step(screen: _Screen, position: Position, joins: bool = False) -> float:
    """Сколько спать до следующего вопроса приёмнику.

    Между словом ``PLAYING`` и доказанным кадром приёмник спрашивается чаще: при шаге
    2 с строка «старт NN с» запаздывала за кадром на 1.9-3.8 с (:data:`FIRST_FRAME_POLL`).
    До слова ``PLAYING`` кадру взяться неоткуда, на паузе и в темноте указатель не
    двигается - там окна старта нет, и шаг обычный.

    Второе окно - последние :data:`END_POLL_WINDOW` секунд серии, за которой есть следующая
    (``joins``): конец потока показ узнаёт только на круге опроса, и следующая серия ждала
    его до двух секунд. У фильма и последней серии стыка нет - и учащать незачем.
    """
    if joins and position.playing and 0.0 < position.dur - position.pos <= END_POLL_WINDOW:
        return FIRST_FRAME_POLL
    if screen.seen or screen.still_at < 0 or position.state in {"PAUSED", "IDLE"}:
        return POLL_SECONDS
    return FIRST_FRAME_POLL
