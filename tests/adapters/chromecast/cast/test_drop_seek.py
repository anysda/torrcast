"""Закрытие перемотки, кончившейся ничем: записью, а не молчанием."""

from __future__ import annotations

from tests.adapters.chromecast.cast.wired import Wired
from tests.fakes.journal import Tape
from torrcast.adapters.chromecast.cast.drop_seek import _drop_seek


def test_a_seek_that_never_showed_a_picture_is_written_down(
    tape: Tape,
) -> None:
    """«Нет строки в ленте» пришлось бы читать как «перемотки не было», а она была.

    Ждать сдвига указателя вечно нельзя: сессия обрывается, сторож перебивает прыжок
    нуджем, человек мотает второй раз. Кончившаяся ничем перемотка - это и есть худший
    исход, ради которого метрику заводили.
    """
    receiver = Wired()
    receiver._seek_from, receiver._seek_to, receiver._seek_since = 100.0, 900.0, 5.0

    _drop_seek(receiver, "сессия оборвалась")

    assert tape.events() == ["seek"]
    (told,) = tape.named("seek")
    assert (told["wait"], told["why"]) == (None, "сессия оборвалась")
    assert receiver._seek_since == 0.0, "перемотка закрыта - второй раз о ней не пишем"


def test_there_is_nothing_to_close_when_no_seek_is_open(tape: Tape) -> None:
    """Открытой перемотки нет - и записи быть не должно: лента не место для пустых строк."""
    receiver = Wired()

    _drop_seek(receiver, "сессия оборвалась")

    assert tape.events() == []
