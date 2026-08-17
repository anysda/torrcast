"""Все приёмники, каких видно с этого хоста: mDNS и обход подсетей разом.

Зовёт его меню выбора приёмника через порт поиска, и больше никто."""

from __future__ import annotations

import ipaddress
from concurrent.futures import ThreadPoolExecutor

from torrcast.adapters.chromecast import scan as _scan
from torrcast.adapters.chromecast.scan.alive import PROBE_TIMEOUT
from torrcast.adapters.chromecast.scan.by_mdns import MDNS_TIMEOUT
from torrcast.adapters.chromecast.scan.by_scan import BUDGET, WORKERS
from torrcast.adapters.chromecast.scan.device import Device
from torrcast.adapters.chromecast.scan.found import Found
from torrcast.adapters.chromecast.scan.subnets import MAX_HOSTS


def find(
    mdns_timeout: float = MDNS_TIMEOUT,
    timeout: float = PROBE_TIMEOUT,
    limit: int = MAX_HOSTS,
    budget: float = BUDGET,
) -> Found:
    """Все приёмники, каких видно с этого хоста: mDNS и обход подсетей разом.

    Оба способа идут **параллельно**: mDNS ждёт свои несколько секунд молча, и тратить
    их последовательно перед обходом незачем - общее время равно большему из двух, а не
    сумме.

    Слияние по адресу: одно устройство находится обоими способами сразу, и вторым
    пунктом в меню оно появляться не должно. Имя от mDNS выигрывает - оно то самое, что
    человек видит в настройках телевизора.
    """
    nets = _scan.interfaces()
    ours = {net.address for net in nets}
    networks, huge = _scan.subnets(nets, limit=limit)
    notes = [line for line in (_scan.skipped(huge),) if line]
    with ThreadPoolExecutor(max_workers=2) as pool:
        listening = pool.submit(_scan.by_mdns, mdns_timeout)
        scanning = pool.submit(_scan.by_scan, _scan.hosts(networks, ours), timeout, WORKERS, budget)
        heard = listening.result()
        addresses = scanning.result()
    if heard.note:  # почему mDNS пуст: нет модуля, нет мультикаста или тишина в эфире
        notes.append(heard.note)
    named_by_scan: list[Device] = []
    known = {device.address for device in heard.devices}
    fresh = [address for address in addresses if address not in known]
    if fresh:
        with ThreadPoolExecutor(max_workers=min(WORKERS, len(fresh))) as pool:
            named_by_scan = list(pool.map(_scan.named, fresh))
    devices = {device.address: device for device in named_by_scan}
    for device in heard.devices:  # имя от mDNS перебивает добытое обходом
        devices[device.address] = device
    order = sorted(devices.values(), key=lambda device: _key(device.address))
    return Found(devices=order, notes=notes)


def _key(address: str) -> tuple[int, ...]:
    """Ключ сортировки адреса: по числам, а не по строке - иначе .10 встаёт перед .9."""
    try:
        return (0, int(ipaddress.ip_address(address)))
    except ValueError:
        return (1, 0)
