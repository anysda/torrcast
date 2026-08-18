"""Параллельный обход адресов: там, куда идёт маршрут, приёмник виден и без mDNS.

Зовёт его поиск приёмников; каждый адрес щупает :func:`alive`."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Final

from torrcast.adapters.chromecast.scan.alive import PROBE_TIMEOUT, alive

#: Сколько адресов щупаем разом. Упирается не в процессор, а в сокеты и таймауты.
WORKERS: Final = 128
#: Общий бюджет обхода, секунды: сколько бы подсетей ни оказалось, ждать дольше нельзя.
BUDGET: Final = 25.0


def by_scan(
    addresses: list[str],
    timeout: float = PROBE_TIMEOUT,
    workers: int = WORKERS,
    budget: float = BUDGET,
    *,
    probe_address: Callable[..., bool] = alive,
) -> list[str]:
    """Обойти адреса параллельно и вернуть те, где живой приёмник.

    Параллельность тут не оптимизация, а условие пригодности: последовательный обход
    ``/24`` с секундным таймаутом - это четыре минуты, то есть никто этим пользоваться
    не станет. Бюджет - второй предохранитель: сколько бы подсетей ни было, ждать
    дольше нельзя, лучше показать найденное.

    ⚠️ Щуп адреса - настоящее TLS-рукопожатие, и на стенде его не бывает: он приезжает
    сюда аргументом с боевым умолчанием, а не спрашивается у пакета по имени.
    """
    if not addresses:
        return []
    deadline = time.monotonic() + budget
    hits: list[str] = []

    def probe(address: str) -> str:
        if time.monotonic() > deadline:
            return ""
        return address if probe_address(address, timeout=timeout) else ""

    with ThreadPoolExecutor(max_workers=min(workers, len(addresses))) as pool:
        for answer in pool.map(probe, addresses):
            if answer:
                hits.append(answer)
    return hits
