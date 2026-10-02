"""TCP-дозвон с запасной попыткой: потерянный SYN не ждёт повтора ядра.

Замер 02-10-2026 с машин домашней сети: 10-60% новых соединений к подсказчику IMDb,
Википедии и ``m.media-amazon.com`` теряли первый пакет дозвона, и ядро повторяло его
через 1, 3 и 7 с, а нормальный дозвон там 18-26 мс. Шесть картин ряда звонят IMDb разом,
и четыре из восьми запросов «призрака в доспехах» упирались в срок подсказчика 4 с с
ответом, который сам сервер отдал бы за десятые доли секунды; полоса хоста стояла
занятой всё это время.

Поэтому дозвон не ждёт ядро: каждые :data:`HEDGE` секунд без ответа уходит ещё одна
попытка с новым портом, прежние продолжают ждать, и берётся первая состоявшаяся. Отказ
сервера (RST, нет маршрута) - это ответ, а не потеря: он отдаётся сразу, как и прежде.
"""

from __future__ import annotations

import errno
import os
import selectors
import socket
import time
from typing import Final

#: Сколько ждём одну попытку дозвона до запасной, секунды. Живой дозвон тут 18-50 мс, а
#: попытка терялась в 37-40% случаев: с шагом 0.3 с дольше 0.5 с звонили 6-10 из 40, с шагом
#: 0.15 с - ни один (худший 0.46 с), стенд 02-10-2026, IMDb, m.media-amazon, ru.wikipedia.
HEDGE: Final = 0.15
#: Сколько попыток дозвона живут разом: потом до срока ждут повтора ядра уже начатые.
ATTEMPTS: Final = 8


def dial(address: str, port: int, timeout: float) -> socket.socket:
    """Соединение с ``address:port`` за ``timeout``; как :func:`socket.create_connection`.

    Состоявшийся сокет блокирующий, со сроком ``timeout`` на дальнейшие операции.
    Не состоялось к сроку - :class:`TimeoutError`, как у ядра.
    """
    deadline = time.monotonic() + timeout
    tries: list[socket.socket] = []
    chooser = selectors.DefaultSelector()
    try:
        while True:
            now = time.monotonic()
            if deadline <= now:
                raise TimeoutError("timed out")
            if len(tries) < ATTEMPTS:
                tries.append(_attempt(address, port, chooser))
            wait = deadline - now if len(tries) >= ATTEMPTS else min(HEDGE, deadline - now)
            until = time.monotonic() + wait
            while (left := until - time.monotonic()) > 0:
                for key, _ in chooser.select(left):
                    won: socket.socket = key.fileobj  # type: ignore[assignment]
                    fault = won.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                    if fault:
                        raise OSError(fault, os.strerror(fault))
                    chooser.unregister(won)
                    tries.remove(won)
                    won.setblocking(True)
                    won.settimeout(timeout)
                    return won
    finally:
        chooser.close()
        for one in tries:
            one.close()


def _attempt(address: str, port: int, chooser: selectors.BaseSelector) -> socket.socket:
    """Одна попытка: SYN ушёл, ответ ждёт ``chooser``; мгновенный отказ поднимается."""
    one = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    one.setblocking(False)
    fault = one.connect_ex((address, port))
    if fault not in (0, errno.EINPROGRESS):
        one.close()
        raise OSError(fault, os.strerror(fault))
    chooser.register(one, selectors.EVENT_WRITE)
    return one


__all__ = ["ATTEMPTS", "HEDGE", "dial"]
