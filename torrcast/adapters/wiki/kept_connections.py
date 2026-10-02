"""Живые соединения по хостам: новое соединение на каждый запрос дома стоило секунд.

Холодная полка спрашивает обложки десятками запросов к полудюжине хостов. Каждый запрос
открывал свой TCP и TLS, и домашняя сеть теряла часть этих SYN: повтор ядра приходит через
1, 3, 7 с, и полоса хоста всё это время занята ожиданием соединения, а не ответом. Пока
соединение живо и сервер его не закрыл, следующий запрос к тому же хосту идёт по нему.

Хранится только соединение, чей ответ дочитан и сервер не сказал «закрою»: иначе в нём
остался бы хвост чужого ответа. Простоявшее дольше :data:`FRESH_FOR` не берётся - такое
мог молча забыть шлюз, и запрос висел бы до своего срока вместо быстрого отказа.

Соединение к хосту из :data:`USES` закрывается, отслужив своё число ответов: из дома
соединение к подсказчику IMDb глохло насовсем на 9-10-м запросе (замер 02-10-2026 на стенде:
30 затыков на 360 запросов, все на этом месте; с новым соединением после шести ответов - 0 на
360), и запрос ждал свой срок до отказа. Остальным хостам срока нет: у CDN картинок IMDb затык
приходится как раз на НОВОЕ соединение (тот же замер: 5 на 240 без смены, 16 на 240 со сменой
после шести), и смена там только множила бы затыки.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any, Final

#: Сколько секунд простоя соединение ещё считается живым.
FRESH_FOR: Final = 15.0
#: Сколько ответов соединение отдаёт хосту, прежде чем уйти: затык дома приходил на 9-10-м.
USES: Final = {"v3.sg.media-imdb.com": 6}
#: Сколько простаивающих соединений держится на один хост; полос у хоста пять.
KEPT_PER_HOST: Final = 5


class KeptConnections:
    """Простаивающие соединения по хостам; берёт их один поток за раз."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._idle: dict[str, list[tuple[float, Any]]] = {}
        self._lock = threading.Lock()

    def take(self, host: str) -> Any | None:
        """Живое соединение к хосту или ``None``; протухшие закрываются здесь же."""
        stale: list[Any] = []
        found = None
        with self._lock:
            idle = self._idle.get(host, [])
            while idle and found is None:
                since, connection = idle.pop()
                if self.clock() - since <= FRESH_FOR:
                    found = connection
                else:
                    stale.append(connection)
        for connection in stale:
            connection.close()
        return found

    def give(self, host: str, connection: Any, response: Any) -> None:
        """Вернуть соединение после ответа: дочитанное и не закрываемое сервером - хранится."""
        connection.answered = getattr(connection, "answered", 0) + 1
        reusable = getattr(response, "will_close", True) is False and bool(
            getattr(response, "isclosed", lambda: False)()
        )
        reusable = reusable and connection.answered < USES.get(host, connection.answered + 1)
        if reusable:
            with self._lock:
                idle = self._idle.setdefault(host, [])
                if len(idle) < KEPT_PER_HOST:
                    idle.append((self.clock(), connection))
                    return
        connection.close()


__all__ = ["FRESH_FOR", "KEPT_PER_HOST", "USES", "KeptConnections"]
