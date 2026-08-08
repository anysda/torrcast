"""Поиск приёмников Chromecast-протокола в сети - чтобы адрес ТВ не пришлось знать.

Настройка после установки звучала так: «узнай где-то IP телевизора и передай его
``cast --tv <ip>``». Узнать его негде: в меню ТВ адрес спрятан через три экрана, а в
роутер пускают не всех. Поэтому ``cast --tv`` без адреса ищет приёмники сам, и человек
выбирает свой телевизор номером из списка.

Ищем **двумя** способами сразу, потому что поодиночке каждый слеп:

* штатный discovery pychromecast (mDNS/zeroconf) - он единственный знает человеческие
  имена («Samsung Q70D»), но mDNS это мультикаст, и через маршрутизатор он не идёт: у
  хоста бывает отдельная нога в сегмент телевизора, где имя услышать некому;
* обход адресов своих подсетей с проверкой порта 8009 - он ходит везде, куда идёт
  маршрут, но сам по себе имени не знает.

Найденное сливается по адресу: имя от mDNS выигрывает, адрес остаётся один.

⚠️ **Открытый порт - ещё не приёмник.** Проверять коннектом мало: транзитный VPN на
исходящем канале отвечает SYN-ACK на любой порт любого адреса, и тогда «нашлось 254
телевизора». Поэтому признаком служит не коннект, а **состоявшееся TLS-рукопожатие** на
8009 (:func:`alive`): молчащая заглушка ServerHello не пришлёт. Дальше запрашивается имя
(:func:`named`) - обычным HTTP-опросом устройства, без единой команды показа: обнаружение
не имеет права ничего запускать на чужом экране.
"""

from __future__ import annotations

import ipaddress
import socket
import ssl
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Final

__all__ = [
    "CAST_PORT",
    "Device",
    "Found",
    "Net",
    "alive",
    "by_mdns",
    "by_scan",
    "find",
    "hosts",
    "interfaces",
    "named",
    "skipped",
    "subnets",
]

#: Порт управления Chromecast: открыт даже в standby, коннект будит ТВ.
CAST_PORT: Final = 8009
#: Сколько ждём коннекта и рукопожатия на один адрес. Секунда - это уже щедро для
#: своей же подсети, а умножается она на длину подсети, делённую на число потоков.
PROBE_TIMEOUT: Final = 1.0
#: Сколько слушаем mDNS. Приёмник отвечает на первый же запрос, дальше идёт тишина.
MDNS_TIMEOUT: Final = 4.0
#: Сколько ждём ответа на опрос имени: имя - украшение, ради него ждать некогда.
NAME_TIMEOUT: Final = 3.0
#: Сколько адресов щупаем разом. Упирается не в процессор, а в сокеты и таймауты.
WORKERS: Final = 128
#: Потолок одной подсети. ``/24`` (254 адреса) проходит, ``/16`` (65534) - нет: обход
#: такой сети занял бы минуты, а телевизор в ней всё равно ищут не перебором.
MAX_HOSTS: Final = 1024
#: Общий бюджет обхода, секунды: сколько бы подсетей ни оказалось, ждать дольше нельзя.
BUDGET: Final = 25.0

_SIOCGIFADDR: Final = 0x8915
_SIOCGIFNETMASK: Final = 0x891B


@dataclass(frozen=True, slots=True)
class Device:
    """Найденный приёмник: адрес обязателен, имя - как повезёт."""

    address: str
    name: str = ""
    model: str = ""
    #: Кто нашёл: ``mdns`` (по имени) или ``скан`` (по порту 8009).
    how: str = ""

    @property
    def title(self) -> str:
        """Как назвать пункт меню: имя, за неимением - модель, за неимением - «приёмник».

        Безымянный пункт всё равно выбираем: адрес рядом, и человек узнаёт свой
        телевизор по нему. Пустая строка в меню была бы хуже честного «приёмник».
        """
        return self.name or self.model or "приёмник"


@dataclass(frozen=True, slots=True)
class Net:
    """Нога хоста: имя интерфейса, наш адрес на нём и маска."""

    name: str
    address: str
    mask: str


@dataclass(slots=True)
class Found:
    """Итог поиска: приёмники и честные строки о том, чего мы не смотрели."""

    devices: list[Device] = field(default_factory=list)
    #: Пропущенные подсети и прочее, о чём человеку надо сказать вслух, а не умолчать.
    notes: list[str] = field(default_factory=list)


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


def subnets(nets: list[Net], limit: int = MAX_HOSTS) -> tuple[list[str], list[str]]:
    """Подсети, годные к обходу, и отдельно - те, что шире потолка.

    Отсекаем то, где искать нечего или дорого: петлю, link-local, ``/32`` (точка-точка,
    соседей нет по определению) и сети шире потолка. Потолок - не вкусовщина: ``/16``
    это 65534 адреса, то есть минуты обхода вместо секунд, и молча уйти в такой обход
    хуже, чем честно сказать «эту подсеть не смотрю, задай адрес руками».

    Про широкие возвращаем не текст, а сами подсети: сказать о них надо **одной** строкой
    (:func:`skipped`). На хосте с docker'ом таких сетей сразу три, и три одинаковых
    абзаца перед меню - это шум, за которым не видно самого списка.
    """
    seen: set[str] = set()
    good: list[str] = []
    huge: list[str] = []
    for net in nets:
        try:
            network = ipaddress.ip_network(f"{net.address}/{net.mask}", strict=False)
        except ValueError:
            continue
        if network.is_loopback or network.is_link_local or network.is_multicast:
            continue
        if network.prefixlen >= 31:  # точка-точка: обходить в ней некого
            continue
        key = str(network)
        if key in seen:
            continue
        seen.add(key)
        if network.num_addresses - 2 > limit:
            huge.append(key)
            continue
        good.append(key)
    return good, huge


def skipped(huge: list[str]) -> str:
    """Одна строка о подсетях, которые мы обходить не стали. Пусто - и говорить не о чем."""
    if not huge:
        return ""
    return (
        f"слишком большие подсети не обхожу: {', '.join(huge)} - "
        "если телевизор в одной из них, задай его адрес руками: cast --tv <ip>"
    )


def hosts(networks: list[str], ours: set[str]) -> list[str]:
    """Адреса подсетей к обходу, без наших собственных: сами себе мы не телевизор."""
    out: list[str] = []
    for key in networks:
        for address in ipaddress.ip_network(key).hosts():
            text = str(address)
            if text not in ours:
                out.append(text)
    return out


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


def named(address: str, timeout: float = NAME_TIMEOUT) -> Device:
    """Имя и модель устройства по адресу - опросом самого устройства, без единой команды.

    Спрашиваем ``pychromecast`` - тот же опрос, каким он сам разбирает найденные по
    адресу устройства: обычный HTTP к странице сведений. Ни соединения показа, ни
    ``LOAD``, ни пультовых команд здесь нет и быть не должно - обнаружение не имеет
    права трогать чужой экран.

    Устройство не представилось (не отвечает, отвечает не так) - возвращаем пункт без
    имени: адрес у него всё равно есть, и в меню он попадёт.
    """
    try:
        from pychromecast.dial import get_device_info
    except ImportError:  # pragma: no cover - pychromecast стоит зависимостью
        return Device(address=address, how="скан")
    status = None
    with suppress(Exception):
        status = get_device_info(address, timeout=timeout)
    if status is None:
        return Device(address=address, how="скан")
    return Device(
        address=address,
        name=str(status.friendly_name or ""),
        model=str(status.model_name or ""),
        how="скан",
    )


def by_mdns(timeout: float = MDNS_TIMEOUT) -> list[Device]:
    """Приёмники, которые сами объявили о себе по mDNS: тут и берутся человеческие имена.

    Слушаем строго IPv4: на хосте без внешнего IPv6 сокет уходит в SYN-SENT и висит
    там дольше всего нашего поиска.

    Любой сбой zeroconf (нет мультикаста, чужой namespace, занятый порт) - это не отказ
    поиска: остаётся обход подсетей, и он найдёт то же самое, только без имён.
    """
    try:
        import zeroconf
        from pychromecast.discovery import CastBrowser, SimpleCastListener
    except ImportError:  # pragma: no cover - pychromecast стоит зависимостью
        return []
    try:
        zconf = zeroconf.Zeroconf(ip_version=zeroconf.IPVersion.V4Only)
    except Exception:
        return []
    browser = CastBrowser(SimpleCastListener(), zconf)
    found: list[Device] = []
    try:
        browser.start_discovery()
        time.sleep(timeout)
        for info in list(browser.devices.values()):
            if info.host:
                found.append(
                    Device(
                        address=str(info.host),
                        name=str(info.friendly_name or ""),
                        model=str(info.model_name or ""),
                        how="mdns",
                    )
                )
    except Exception:
        return found
    finally:
        with suppress(Exception):
            browser.stop_discovery()
        with suppress(Exception):
            zconf.close()
    return found


def by_scan(
    addresses: list[str],
    timeout: float = PROBE_TIMEOUT,
    workers: int = WORKERS,
    budget: float = BUDGET,
) -> list[str]:
    """Обойти адреса параллельно и вернуть те, где живой приёмник.

    Параллельность тут не оптимизация, а условие пригодности: последовательный обход
    ``/24`` с секундным таймаутом - это четыре минуты, то есть никто этим пользоваться
    не станет. Бюджет - второй предохранитель: сколько бы подсетей ни было, ждать
    дольше нельзя, лучше показать найденное.
    """
    if not addresses:
        return []
    deadline = time.monotonic() + budget
    hits: list[str] = []

    def probe(address: str) -> str:
        if time.monotonic() > deadline:
            return ""
        return address if alive(address, timeout=timeout) else ""

    with ThreadPoolExecutor(max_workers=min(workers, len(addresses))) as pool:
        for answer in pool.map(probe, addresses):
            if answer:
                hits.append(answer)
    return hits


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
    nets = interfaces()
    ours = {net.address for net in nets}
    networks, huge = subnets(nets, limit=limit)
    notes = [line for line in (skipped(huge),) if line]
    with ThreadPoolExecutor(max_workers=2) as pool:
        listening = pool.submit(by_mdns, mdns_timeout)
        scanning = pool.submit(by_scan, hosts(networks, ours), timeout, WORKERS, budget)
        heard = listening.result()
        addresses = scanning.result()
    named_by_scan: list[Device] = []
    known = {device.address for device in heard}
    fresh = [address for address in addresses if address not in known]
    if fresh:
        with ThreadPoolExecutor(max_workers=min(WORKERS, len(fresh))) as pool:
            named_by_scan = list(pool.map(named, fresh))
    devices = {device.address: device for device in named_by_scan}
    for device in heard:  # имя от mDNS перебивает добытое обходом
        devices[device.address] = device
    order = sorted(devices.values(), key=lambda device: _key(device.address))
    return Found(devices=order, notes=notes)


def _key(address: str) -> tuple[int, ...]:
    """Ключ сортировки адреса: по числам, а не по строке - иначе .10 встаёт перед .9."""
    try:
        return (0, int(ipaddress.ip_address(address)))
    except ValueError:
        return (1, 0)
