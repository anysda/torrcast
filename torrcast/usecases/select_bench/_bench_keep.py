"""Держимая раздача не закрывается TorrServer по тайм-ауту, пока её ждут карточка или показ.

TorrServer закрывает раздачу без читателей, когда истёк её срок, а срок продлевает любой
запрос ``get`` по хэшу: на ``TorrentDisconnectTimeout``, но не больше минуты (MatriX.143,
``server/torr/apihelper.go`` ``GetTorrent``, ``server/torr/torrent.go`` ``expired``).
Поэтому держатель спрашивает файлы раздачи втрое чаще срока, и не дольше потолка.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from typing import Final, Protocol, runtime_checkable

from torrcast.domain.infra_error import InfraError
from torrcast.ports.torrent_engine import TorrentEngine
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.torrent_claims import CLAIMS

#: Сколько держим раздачу открытой после выбора: карточку, брошенную открытой дольше десяти
#: минут, уже не смотрят, а чужой TorrServer не обязан кормить её пирами и кэшем. Вернувшийся
#: заплатит за метаданные секунду-другую, как платил до продления.
KEEP_CEILING: Final = 600.0
#: Дальше минуты ``get`` срок не продлевает, сколько бы ни стояло в настройках.
GET_EXTENDS_AT_MOST: Final = 60.0


@runtime_checkable
class _Timed(Protocol):
    """Служба, которая называет свой срок закрытия раздачи без читателей."""

    def disconnect_timeout(self) -> float: ...


def _keep_step(timeout: float) -> float:
    """Шаг продления: треть срока, чтобы и два пропущенных ответа раздачу не закрыли."""
    return min(timeout, GET_EXTENDS_AT_MOST) / 3


def _keep_open(
    engine: TorrentEngine,
    torrent_hash: str,
    timeout: float,
    held: Callable[[], bool],
    until: Callable[[], float],
    clock: Callable[[], float],
    wait: Callable[[float], object],
) -> int:
    """Продлевать срок раздачи, пока её держат и не вышел потолок; сколько раз продлили."""
    step = _keep_step(timeout)
    asked = 0
    while held() and clock() < until():
        with contextlib.suppress(InfraError):  # служба промолчала: следующий шаг спросит снова
            engine.files(torrent_hash)
        asked += 1
        wait(step)
    return asked


def _bench_keep(
    engine: TorrentEngine,
    chosen: _Prep,
    until: dict[str, float],
    lock: threading.Lock,
    clock: Callable[[], float],
    wait: Callable[[float], object],
) -> None:
    """Продление выбора стенда: держание - отметка раздачи в процессе и не снятый выбор."""
    torrent_hash = chosen.torrent_hash
    try:
        if isinstance(engine, _Timed):
            _keep_open(
                engine,
                torrent_hash,
                engine.disconnect_timeout(),
                lambda: not chosen.dropped and CLAIMS.claimed(torrent_hash),
                lambda: until.get(torrent_hash, 0.0),
                clock,
                wait,
            )
    finally:
        with lock:
            until.pop(torrent_hash, None)
