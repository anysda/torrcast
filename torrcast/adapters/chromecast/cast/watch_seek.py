"""Сторож перемотки: заметить её и померить, через сколько вернулась КАРТИНКА.

Зовёт его опрос места показа на каждом опросе, и только он."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.chromecast.cast.drop_seek import _drop_seek
from torrcast.ports.journal.slot import journal

if TYPE_CHECKING:
    from torrcast.adapters.chromecast.cast.receiver_state import _State


def _watch_seek(rcv: _State, pos: float, state: str) -> None:
    """Заметить перемотку и померить, через сколько после неё вернулась КАРТИНКА.

    Перемотка видна только по позиции: приёмник мотает сам, никакой команды нам при
    этом не приходит. Отличаем её от хода показа по величине прыжка
    (:attr:`SEEK_JUMP`), а от собственного нуджа - по тому, куда прыгнули: сторож
    только что назвал это место сам (:attr:`_nudged_to`).

    🔴 Конец ожидания - СДВИГ УКАЗАТЕЛЯ с места приземления (:attr:`PICTURE_STEP`), а
    не слово ``PLAYING``: приёмник говорит его раньше первого кадра, и метрика,
    верившая слову, писала 0.0 с там, где зритель ждал 6-10 с. Замер на живом Q70D:
    назад 3.8-4.2 с, вперёд 9.3-11.9 с, глубоко в непрогретое 5.2-6.8 с.

    ⚠️ Прыжок засчитывается по позиции, которая УЖЕ уехала, поэтому место приземления
    известно только с этого опроса: ``to`` - это то, куда приёмник встал, а не то, что
    нажали на пульте. Мерить от предыдущей пробы нельзя - на ней указатель ещё стоит
    там, откуда прыгнули.

    ``IDLE`` из счёта выкинут по той же причине, что и в :meth:`position`: у мёртвой
    сессии позиции нет вовсе, и её ноль - не перемотка в начало.
    """
    seen, rcv._seen = rcv._seen, pos
    if state == "IDLE":
        rcv._seen = seen  # позиции не было - и сравнивать в следующий раз не с чем
        _drop_seek(rcv, "сессия оборвалась")
        return
    jumped = seen >= 0.0 and abs(pos - seen) > rcv.SEEK_JUMP
    # Картинку засчитываем только на опросе БЕЗ нового прыжка: иначе вторая перемотка
    # подряд сошла бы за возвращение картинки после первой - указатель-то уехал.
    if rcv._seek_since and not jumped and pos >= rcv._seek_to + rcv.PICTURE_STEP:
        journal().seek(
            frm=rcv._seek_from,
            to=rcv._seek_to,
            wait=rcv.clock.monotonic() - rcv._seek_since,
        )
        rcv._seek_since = 0.0
    if not jumped:
        return
    if rcv._nudged_to >= 0.0 and abs(pos - rcv._nudged_to) <= rcv.SEEK_JUMP:
        rcv._nudged_to = -1.0  # прыжок наш: сторож уже записал его как нудж
        return
    _drop_seek(rcv, "следом пришла ещё одна перемотка")
    rcv._seek_from, rcv._seek_to = seen, pos
    rcv._seek_since = rcv.clock.monotonic()
