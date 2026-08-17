"""Признак приёмника на адресе - состоявшееся TLS-рукопожатие, а не открытый порт.

Спрашивает его обход подсетей на каждом адресе."""

from __future__ import annotations

import socket
import ssl
from typing import Final

#: Порт управления Chromecast: открыт даже в standby, коннект будит ТВ.
CAST_PORT: Final = 8009
#: Сколько ждём коннекта и рукопожатия на один адрес. Секунда - это уже щедро для
#: своей же подсети, а умножается она на длину подсети, делённую на число потоков.
PROBE_TIMEOUT: Final = 1.0


def alive(address: str, port: int = CAST_PORT, timeout: float = PROBE_TIMEOUT) -> bool:
    """Отвечает ли по этому адресу настоящий приёмник.

    Признак - **состоявшееся TLS-рукопожатие**, а не открытый порт. Разница
    принципиальная: сетевой посредник (прокси, транзитный VPN) охотно отвечает SYN-ACK
    за любой адрес, и проверка коннектом объявила бы приёмником каждый адрес подсети.
    Рукопожатие такой посредник не изобразит - ServerHello брать неоткуда.

    Серт приёмника не проверяем (он самоподписанный, у устройств Google - свой корень):
    нам нужен факт «на том конце живой TLS», а не доверие. Ровно такой же контекст
    поднимает у себя pychromecast перед показом.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with (
            socket.create_connection((address, port), timeout=timeout) as raw,
            context.wrap_socket(raw) as tls,
        ):
            return bool(tls.version())
    except (OSError, ssl.SSLError, ValueError):
        return False
