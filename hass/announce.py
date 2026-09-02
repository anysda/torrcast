"""Объявление моста по mDNS: Home Assistant находит его сам, без ввода адреса руками.

Имя службы держит имя хоста. В одной сети живут два стенда, и оба поднимают мост; без
имени хоста второй перебивал бы первого - zeroconf развёл бы их суффиксом ``-2``, и
карточка после перезапуска цеплялась бы то к одному, то к другому.
"""

from __future__ import annotations

import socket
from typing import Any

#: Тип службы. Своё имя, а не ``_http._tcp``: искать нас будет одна интеграция.
SERVICE = "_torrcast._tcp.local."
#: Якорь для вопроса «каким адресом нас видно», когда телевизор ещё не назван. Адрес из
#: RFC 5737 не бывает своим ни в одной домашней сети, поэтому ядро отвечает адресом
#: интерфейса маршрута по умолчанию. Пакета в него не уходит ни одного.
ANCHOR = "192.0.2.1"


def _address(tv: str) -> str:
    """Адрес, которым нас видно из сети; ищется тем же способом, что и для раздачи HLS."""
    from torrcast.adapters.http_server.our_address import our_address

    return our_address(tv or ANCHOR)


class Announce:
    """Запись службы в mDNS; снимается по :meth:`close` вместе с уходом моста."""

    def __init__(self, port: int, *, version: str, tv: str, host: str = "") -> None:
        self._port = port
        self._version = version
        self._tv = tv
        self._host = host or socket.gethostname().split(".")[0]
        self._zeroconf: Any = None
        self._info: Any = None

    @property
    def name(self) -> str:
        """Имя службы: имя хоста внутри, чтобы два стенда не спорили за одно имя."""
        return f"torrcast-{self._host}.{SERVICE}"

    def open(self) -> bool:
        """Объявить мост; сеть не дала объявить - ``False``, и мост всё равно служит.

        Отказ mDNS не повод не отвечать на запросы: адрес моста можно вписать в карточку
        и руками, а вот молча умереть от чужой сети мост права не имеет.
        """
        from zeroconf import ServiceInfo, Zeroconf

        found = _address(self._tv)
        if not found:
            return False
        self._zeroconf = Zeroconf()
        self._info = ServiceInfo(
            SERVICE,
            self.name,
            addresses=[socket.inet_aton(found)],
            port=self._port,
            properties={"version": self._version, "tv": self._tv},
            server=f"{self._host}.local.",
        )
        try:
            self._zeroconf.register_service(self._info)
        except Exception:
            self.close()
            return False
        return True

    def close(self) -> None:
        """Снять запись: ушедший мост не должен остаться в списке устройств."""
        zeroconf, info, self._zeroconf, self._info = self._zeroconf, self._info, None, None
        if zeroconf is None:
            return
        try:
            if info is not None:
                zeroconf.unregister_service(info)
        finally:
            zeroconf.close()
