"""Снятие каста и, по просьбе, закрытие приложения приёмника - только своего.

Зовёт его конец показа: между сериями без закрытия, на конце сеанса - с ним."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.adapters.chromecast.cast.receiver_talk import _Talk


def _stop(rcv: _Talk, quit_app: bool = False) -> None:
    """Снять каст, а по ``quit_app`` — ещё и закрыть приложение приёмника.

    Зачем закрывать: ``media_controller.stop()`` гасит только показ, а Default Media
    Receiver остаётся на экране иконкой и висит там до собственного таймаута простоя —
    пользователь видит её после `cast stop` и после титров, и она же оттягивает
    автовыключение ТВ. ``quit_app`` возвращает телевизор в исходное состояние
    (``app_id`` пустеет либо становится Backdrop) сразу.

    ⚠️ Закрываем **только свою** сессию (:meth:`_ours`): на том же ТВ могут жить другие
    сендеры, и кастят они через тот же Default Media Receiver. Чужой показ снимать
    нельзя — ни ``stop``, ни тем более ``quit_app``.

    Соединение после закрытия рвём сами: сендер, переживший своё приложение, для
    следующего показа — тот самый «второй pychromecast», из-за которого приёмник
    отдаёт пустой MEDIA_STATUS (см. предупреждение в докстринге класса).

    🔴 Закрывая приложение, ``STOP`` медиасессии не шлём вовсе. ``media_controller.stop()``
    ждёт ответа приёмника синхронно (``WaitResponse``, бюджет 10 с), и ровно на это
    ожидание приложение задерживалось на экране: ``QUIT_APP`` уходил только после ответа.
    Замер на приставке 02-09-2026, три прогона: round-trip ``STOP`` — 167, 242 и 246 мс, и
    все они целиком стояли между `cast stop` и чистым экраном. Гасить показ отдельно тут
    незачем: приложение уносит с собой и сессию, и картинку. На стыке серий ``STOP``
    остаётся: там приложение живёт дальше, и медиасессию надо закрыть явно.
    """
    if rcv._cast is None or not rcv._ours():
        return
    if not quit_app:
        with contextlib.suppress(Exception):
            rcv._cast.media_controller.stop()
        return  # показ передают следующей серии - приложение ей и достанется
    with contextlib.suppress(Exception):
        rcv._cast.quit_app()
    with contextlib.suppress(Exception):
        rcv._cast.disconnect()
    rcv._cast, rcv._session = None, ""
