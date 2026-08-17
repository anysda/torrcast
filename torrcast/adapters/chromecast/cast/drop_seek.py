"""Закрыть перемотку, у которой картинки так и не случилось, - записью, а не молчанием.

Зовут это сторож перемотки и сторож подвиса, перебивающий прыжок нуджем."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.ports.journal import journal

if TYPE_CHECKING:
    from torrcast.adapters.chromecast.cast.receiver_state import _State


def _drop_seek(rcv: _State, why: str) -> None:
    """Закрыть перемотку, у которой картинки так и не случилось, - записью, а не молчанием.

    Ждать сдвига указателя вечно нельзя: сессия обрывается, сторож перебивает прыжок
    нуджем, человек мотает второй раз. Если в таких случаях не писать ничего, «нет
    строки в ленте» придётся читать как «перемотки не было», а она была и кончилась
    ничем - это и есть худший исход, ради которого метрику заводили.
    """
    if not rcv._seek_since:
        return
    journal().seek(frm=rcv._seek_from, to=rcv._seek_to, wait=None, why=why)
    rcv._seek_since = 0.0
