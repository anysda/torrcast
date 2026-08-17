"""Ноги хоста с адресом IPv4 - спросом у ядра, а не разбором чужого вывода.

Спрашивает их поиск приёмников: по ним и считаются подсети к обходу."""

from __future__ import annotations

import socket
import struct
from typing import Final

from torrcast.adapters.chromecast.scan.net import Net

#: Запросы ioctl про адрес и маску интерфейса: они и есть весь «разбор» вместо утилит.
_SIOCGIFADDR: Final = 0x8915
_SIOCGIFNETMASK: Final = 0x891B


def interfaces() -> list[Net]:
    """Ноги хоста с адресом IPv4: имя, адрес, маска.

    Спрашиваем ядро ioctl'ом по каждому интерфейсу, а не разбираем вывод ``ip``: лишней
    зависимости от формата чужой утилиты в пути установки быть не должно. IPv6 не
    трогаем сознательно - Chromecast-приёмники живут на IPv4, а на хосте без внешнего
    IPv6 попытка ходить по нему кончается зависанием в SYN-SENT.
    """
    import fcntl

    nets: list[Net] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for _index, name in socket.if_nameindex():
            packed = struct.pack("256s", name.encode()[:15])
            try:
                address = socket.inet_ntoa(fcntl.ioctl(sock.fileno(), _SIOCGIFADDR, packed)[20:24])
                mask = socket.inet_ntoa(fcntl.ioctl(sock.fileno(), _SIOCGIFNETMASK, packed)[20:24])
            except OSError:  # интерфейс без адреса IPv4 (down, только IPv6, tun без ip)
                continue
            nets.append(Net(name=name, address=address, mask=mask))
    finally:
        sock.close()
    return nets
