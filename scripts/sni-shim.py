#!/usr/bin/env python3
"""Локальный TLS-шим для трекеров, чьё ИМЯ не проходит по TLS.

Часть установки: его ставит и запускает `install.sh`, когда видит, что имя отдаёт
ответ не целиком.

Бывает, что канал режет соединения по имени в SNI: заголовки приходят, а тело
обрывается на первых килобайтах и висит (мелкие ответы проходят, крупные - нет).
Тот же адрес того же CDN, спрошенный под другим именем, отдаёт мегабайт за доли
секунды - то есть это не MTU, не HTTP/2 и не сторона трекера.

Имя трекера прибивается в `/etc/hosts` к этому шиму, а шим ходит к origin сам и
имени в TLS не показывает:

* `direct` - стучится прямо на IP origin'а. Для IP-адреса SNI не отправляется вовсе
  (ни этим шимом, ни curl: имени в открытой части рукопожатия просто нет), а куда
  идти - origin понимает по заголовку `Host`. Адрес шим спрашивает у DNS сам, минуя
  `/etc/hosts`: там это имя уже прибито к нему же.
* `https://запасное-имя` - другое имя, ведущее в тот же origin. Нужно там, где без
  SNI origin не отвечает (CDN на общем адресе) и приходится показывать имя, которого
  в списке DPI нет.
* `named` - то же имя, но адрес спрашиваем у DNS сами. Для тех, у кого запасного имени
  нет, а без имени в рукопожатии CDN отвечает 403 (замер на yts.gg: 403 за 0.1 с с
  обоих адресов). Показать имя обычным способом нельзя - `getaddrinfo` вернёт нас же
  из `/etc/hosts`, - поэтому адрес берём своим запросом к DNS, а имя остаётся в SNI,
  в `Host` и в проверке серта. Заодно это лечит угон DNS: подставной адрес отдаёт
  самоподписанный серт, проверка его не принимает, и шим уходит на следующий адрес.

К одному хосту шим держит не больше двух запросов зараз: фронт трекера, спрошенный
по IP, столько и тянет, а лишним параллельным отвечает 504 на шестнадцатой секунде -
после серии таких индексер уезжает в бан на три часа. Лишние ждут очереди, а не летят
на хост. Счёт очереди у каждого хоста свой: больной сосед чужие не задерживает, и
одиночный запрос на пустой очереди не ждёт вовсе.

Слушает только петлю; наружу не смотрит и ничего не кэширует.

Дом обхода - этот отдельный скрипт, а не адаптер пакета, и это решение, а не
случайность: процесс у шима свой (systemd держит его сокет сквозь рестарт, чтобы не
рвать входящие соединения), права свои (он правит таблицу имён хоста), а пакету от него
не нужно ни одного вызова - обход поднимается установкой и живёт ниже уровня
приложения. Граница поэтому названа явно и вся она здесь: командная строка и окружение.
Настройки окружения читаются в точке входа (:func:`main`) и в месте использования, а не
на импорте модуля: иначе их нельзя назвать доводом - окружение, выставленное после
импорта, не бралось бы вовсе. Держит границу `tests/test_shim.py`, грузящий скрипт
по пути.

    sni-shim.py <cert> <key> <порт> имя=кандидат[,кандидат…] …
    sni-shim.py --resolve имя …   адреса origin'а мимо `/etc/hosts` (ими щупает установка)
    sni-shim.py --unpin имя …     снять наши строки из `/etc/hosts`

Остальное приезжает окружением, чтобы не городить кавычки в строке запуска юнита:
`TORRCAST_HOSTS`, `TORRCAST_ROUTE_PROBES` (файл `имя|путь|тело` - чем щупать),
`TORRCAST_ROUTE_PAGES` (файл `имя|N` - кому постраничный обход и какого размера
страница), `TORRCAST_ROUTE_PINNED` (что прибито на старте), `TORRCAST_ROUTE_EVERY`
(как часто перерешать, 0 - не перерешать) и пороги пробы `TORRCAST_PROBE_*` - те же,
что у установки.
"""

from __future__ import annotations

import contextlib
import gzip
import http.client
import http.server
import json
import os
import random
import select
import socket
import socketserver
import ssl
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zlib
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

#: Заголовки, которые нельзя переносить как есть: часть про соединение (оно у нас
#: своё), часть мы пересчитываем сами.
_HOP = frozenset(
    {
        "connection",
        "content-length",
        "host",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)
#: Один молчащий кандидат не вправе съесть бюджет до сменной альтернативы.
_TIMEOUT = 5.0
#: Весь перебор маршрута заканчивается раньше личного бюджета индексера (20 с).
_ROUTE_TIMEOUT = 15.0
#: Сколько запросов зараз пускаем на ОДИН хост. Два - потолок, который держит самый
#: слабый из наших фронтов; третий параллельный он уже не обслуживает, а роняет в 504.
_PER_HOST = 2
#: Как часто ждущий слот проверяет, не ушёл ли его клиент.
_QUEUE_POLL = 0.1
#: Сколько соединений ждут своей очереди на ПРИЁМ, пока шим занят предыдущими.
#:
#: 🔴 TC-306. Умолчание :mod:`socketserver` - пять, и оно рассчитано не на нашу нагрузку:
#: за одним поиском стоят четыре индексера, у каждого свои повторы внутри Prowlarr, а
#: поисков бывает и два разом (добор, фолбэк по анимешным). Пять мест на это - счёт из
#: другой задачи. Переполненная очередь приёма на Linux не отвечает отказом, а МОЛЧА
#: роняет SYN, и клиент вместо «занято» получает таймаут - то есть ровно тот отказ
#: канала, который наверху не отличить от «ничего не нашлось».
#: Сотня с лишним стоит одну структуру ядра на место и заведомо перекрывает и повторы,
#: и залп после перезапуска, когда все четверо стучатся разом.
_BACKLOG = 128
#: Сколько ждём от клиента рукопожатия, прежде чем считать его ушедшим. Здоровое TLS
#: по петле укладывается в миллисекунды; десять секунд - это про клиента, у которого
#: канал съел ClientHello, а не про медленного.
_HANDSHAKE = 10.0
#: Насколько верим разобранному адресу origin'а, прежде чем спросить DNS заново.
_DNS_TTL = 300.0
_DNS_TIMEOUT = 5.0

#: Где лежит таблица имён, если окружение не назвало другую. Перебивает её
#: ``TORRCAST_HOSTS``, и читается оно в точке входа (:func:`main`), а не здесь:
#: на импорте настройку нельзя назвать доводом.
_HOSTS = "/etc/hosts"
_LEASE_POLL = 0.25
#: Метка наших строк в ней: по ней и только по ней мы их потом убираем. Чужую строку
#: (например, нарочно прибитый каталог определений Prowlarr) не трогаем никогда.
_PIN_MARK = "# torrcast-shim"
#: Как часто перерешать маршрут умолчанием; перебивает ``TORRCAST_ROUTE_EVERY`` в
#: точке входа. Ноль - не перерешать вовсе (так гоняют тесты).
_WATCH_EVERY = 900.0
#: Сколько проверок ПОДРЯД имя должно ответить целиком, чтобы снять с него обход.
#: Больше одной нарочно: снять обход по одной удачной пробе - это как раз тот дешёвый
#: способ получить дорогую ошибку (молчащий индексер), от которого весь перекос и заведён.
_WATCH_CLEAR = 2
#: Пороги пробы умолчанием - те же, что у установки (`probe_whole` в install.sh,
#: TC-235): судим по ПРОСТОЮ потока, а не по общему времени. Окружение
#: (``TORRCAST_PROBE_*``) перебивает их в месте использования (:func:`probe_direct`).
_PROBE_TIMEOUT = "25"
_PROBE_STALL = "5"
_PROBE_FLOOR = "1024"
_PROBE_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122 Safari/537.36"
)


def _nameservers() -> list[str]:
    """Read IPv4 DNS from resolv.conf, followed by explicit service fallbacks."""
    out: list[str] = []
    try:
        with open("/etc/resolv.conf", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "nameserver" and ":" not in parts[1]:
                    out.append(parts[1])
    except OSError:
        pass
    for server in (os.environ.get("TORRCAST_DNS_FALLBACK") or "").replace(",", " ").split():
        if ":" not in server and server not in out:
            out.append(server)
    return out


def _flush_system_dns() -> None:
    """Make macOS forget answers collected before our hosts change."""
    if os.environ.get("TORRCAST_FLUSH_DNS") != "macos":
        return
    subprocess.run(["/usr/bin/dscacheutil", "-flushcache"], check=False)
    subprocess.run(["/usr/bin/killall", "-HUP", "mDNSResponder"], check=False)


def _skip_name(data: bytes, pos: int) -> int:
    """Перешагнуть имя в DNS-ответе: метки до нуля либо указатель сжатия (2 байта)."""
    while pos < len(data):
        length = data[pos]
        if length == 0:
            return pos + 1
        if length >= 0xC0:
            return pos + 2
        pos += 1 + length
    raise OSError("обрезанный ответ DNS")


def _query(host: str, server: str, rtype: int = 1) -> list[str]:
    """Спросить у DNS адреса имени напрямую, минуя `/etc/hosts` (``rtype`` 1 - A, 28 - AAAA).

    Через `socket.getaddrinfo` нельзя: имя там уже прибито к нам же, и шим ходил бы
    сам к себе. Запрос простой - один вопрос об адресе, ответ разбираем руками.
    """
    ident = random.randrange(1 << 16)  # не крипта: ident отсеивает чужие ответы
    labels = b"".join(bytes([len(p)]) + p for p in host.encode("idna").split(b"."))
    query = struct.pack(">HHHHHH", ident, 0x0100, 1, 0, 0, 0) + labels + b"\0"
    query += struct.pack(">HH", rtype, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(_DNS_TIMEOUT)
        sock.sendto(query, (server, 53))
        data = sock.recv(4096)
    if len(data) < 12 or data[:2] != query[:2]:
        raise OSError("DNS ответил не на наш запрос")
    questions, answers = struct.unpack(">HH", data[4:8])
    pos = 12
    for _ in range(questions):
        pos = _skip_name(data, pos) + 4
    out: list[str] = []
    for _ in range(answers):
        pos = _skip_name(data, pos)
        kind, _cls, _ttl, rdlen = struct.unpack(">HHIH", data[pos : pos + 10])
        pos += 10
        if kind == 1 and rdlen == 4:
            out.append(socket.inet_ntoa(data[pos : pos + 4]))
        elif kind == 28 and rdlen == 16:
            out.append(socket.inet_ntop(socket.AF_INET6, data[pos : pos + 16]))
        pos += rdlen
    return out


class Resolver:
    """Адреса origin'ов: спрашиваем DNS сами и держим разобранное недолгое время.

    🔴 TC-267. Последний удачный ответ помним ОТДЕЛЬНО от свежего и без срока: у
    трекеров, чей единственный кандидат - `direct` или `named`, адрес и есть весь
    маршрут, и минутная немота DNS означала бы для них не «медленнее», а «никак».
    Замер на живой машине: пока рядом шли пробы, DNS перестал отвечать на пять секунд, и
    шим отдал `502 маршрут пуст` на nyaa и rutor разом - у Knaben в тот же миг всё было
    хорошо, потому что у него есть запасное ИМЯ, которому адрес не нужен. Адрес origin'а
    меняется куда реже, чем моргает канал, так что помнить его строго лучше, чем
    оставаться без маршрута.
    """

    def __init__(
        self,
        ttl: float = _DNS_TTL,
        servers: Callable[[], list[str]] = _nameservers,
        ask: Callable[[str, str, int], list[str]] = _query,
    ) -> None:
        #: Откуда берутся резолверы и чем их спрашивают. Боевая пара стоит умолчанием;
        #: подставленная нужна там, где мерят поведение при молчащем DNS.
        self._servers = servers
        self._ask = ask
        self._ttl = ttl
        self._cache: dict[str, tuple[float, list[str]]] = {}
        #: Последнее, что DNS вообще успел про имя сказать. Срока годности нет нарочно.
        self._known: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    def addresses(self, host: str) -> list[str]:
        """Адреса, по которым ходит САМ шим. Только IPv4, и это не упущение.

        🔴 Замер на живой машине: у yts.gg тело по IPv6 встаёт на 16401 Б и висит до
        таймаута с обоих его адресов, а те же данные по IPv4 приезжают целиком за 0.3 с.
        Клиент (Prowlarr) семейство выбирает сам и берёт IPv6 первым, так что «шим
        помогает» тут во многом означает «шим идёт по IPv4».
        """
        with self._lock:
            fresh = self._cache.get(host)
            if fresh and fresh[0] > time.monotonic():
                return fresh[1]
        found: list[str] = []
        for server in self._servers():
            try:
                found = [a for a in self._ask(host, server, 1) if not a.startswith("127.")]
            except (OSError, struct.error, IndexError):
                continue
            if found:
                break
        if not found:
            with self._lock:
                remembered = self._known.get(host)
            if remembered:
                print(f"{host}: DNS молчит, иду по прежнему адресу", file=sys.stderr, flush=True)
                return remembered
            raise OSError(f"DNS не дал адреса для {host}")
        with self._lock:
            self._cache[host] = (time.monotonic() + self._ttl, found)
            self._known[host] = found
        return found

    def client_addresses(self, host: str) -> list[str]:
        """Адреса, на которые ляжет ОБЫЧНЫЙ клиент: по первому на каждое семейство.

        🔴 Этим и только этим щупает :class:`Watch`. Проверять один IPv4, когда клиент
        первым берёт IPv6, значит мерить не ту дорогу: замер на живой машине - проба по
        IPv4 отвечала целиком за 0.3 с, а Prowlarr в тот же миг получал по IPv6 обрыв на
        16401 Б и «Failed to read complete http response». Здоровым имя считается, только
        если отвечают ВСЕ семейства: клиент выбирает не наше мнение, а своё.
        """
        out = self.addresses(host)[:1]
        for server in self._servers():
            try:
                sixth = [a for a in self._ask(host, server, 28) if ":" in a]
            except (OSError, struct.error, IndexError):
                continue
            if sixth:
                out += sixth[:1]
                break
        return out


class Target(NamedTuple):
    """Одна попытка: куда стучаться, проверять ли серт и чей это кандидат.

    ``via`` пусто - соединение встаёт туда, куда ведёт ``base``. Непусто - это адрес,
    на который жмём, а имя из ``base`` остаётся в SNI, в ``Host`` и в проверке серта
    (кандидат ``named``).
    """

    base: str
    verify: bool
    via: str
    number: int


class Route:
    """Один трекер: имя, которое видит Prowlarr, и кандидаты, куда ходить на самом деле."""

    def __init__(
        self, host: str, candidates: list[str], path: str = "", body: str = "", page: int = 0
    ) -> None:
        self.host = host
        self.candidates = candidates
        #: Чем щупать источник напрямую (:class:`Watch`): путь и тело POST. Пусто - имя
        #: перерешать нечем, и маршрут у него остаётся тот, с которым его завели.
        self.path = path
        self.body = body
        #: Размер страницы постраничного обхода (TC-696, см. модульную строку). Ноль -
        #: запросы уходят как пришли, одним ответом.
        self.page = page
        self.current = 0
        #: Места в очереди к ЭТОМУ хосту. Свой счётчик на каждый - в этом весь смысл:
        #: хост, который сейчас болеет, держит только своих ждущих.
        self.gate = threading.BoundedSemaphore(_PER_HOST)

    def targets(self, resolver: Resolver) -> list[Target]:
        """Куда идти, начиная с того кандидата, который сработал в прошлый раз."""
        order = list(range(len(self.candidates)))
        order = order[self.current :] + order[: self.current]
        out: list[Target] = []
        for number in order:
            candidate = self.candidates[number]
            kind, _, mirror = candidate.partition(":")
            if kind not in ("direct", "named"):
                out.append(Target(candidate.rstrip("/"), True, "", number))
                continue
            # `direct:зеркало` - адрес берём у зеркала, а спрашиваем всё равно про своё
            # имя (оно уедет в `Host`). Это второй край того же каталога: имени в
            # рукопожатии нет, так что зеркало здесь - именно адрес, а не другой сайт.
            try:
                found = resolver.addresses(mirror or self.host)
            except OSError:
                continue
            if kind == "direct":  # по адресу и без имени: серт там на чужое имя
                out += [Target(f"https://{ip}", False, "", number) for ip in found]
            else:  # по адресу, но с именем: и SNI, и серт остаются настоящими
                out += [Target(f"https://{self.host}", True, ip, number) for ip in found]
        return out


def _ours(line: str, owned: set[str]) -> bool:
    """Наша ли это строка в `/etc/hosts`.

    Своей считаем помеченную (:data:`_PIN_MARK`) и ровно один вид непомеченной -
    `127.0.0.1 имя` из нашего же списка: так подбираются строки, оставленные прежними
    установками, когда метки ещё не было. Всё прочее - чужое: строка с несколькими
    именами, чужой адрес, нарочно прибитый посторонний хост.
    """
    body = line.split("#")[0].split()
    if not body:
        return False
    if line.rstrip().endswith(_PIN_MARK):
        return True
    return len(body) == 2 and body[0] == "127.0.0.1" and body[1].lower() in owned


def set_pins(path: str, wanted: Iterable[str], owned: Iterable[str]) -> bool:
    """Оставить прибитыми к шиму ровно ``wanted`` из наших имён ``owned``.

    Печатает ``True``, если файл пришлось менять. Идемпотентно и без побочных жертв:
    чужие строки переносятся как есть и в прежнем порядке.
    """
    mine = {h.lower() for h in owned}
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            was = handle.read()
    except OSError:
        return False
    lines = [line for line in was.splitlines() if not _ours(line, mine)]
    addresses = (os.environ.get("TORRCAST_PIN_ADDRESSES") or "127.0.0.1").replace(",", " ").split()
    lines += [f"{address} {host} {_PIN_MARK}" for host in wanted for address in addresses]
    text = "".join(f"{line}\n" for line in lines)
    if text == was:
        return False
    # Сперва подменой файла целиком (в этот миг таблица имён либо старая, либо новая, но
    # не обрезанная), и только если так нельзя - записью на месте: `/etc/hosts` бывает
    # примонтированным снаружи, и подменить его тогда не выйдет.
    spare = f"{path}.torrcast"
    try:
        with open(spare, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(spare, 0o644)
        os.replace(spare, path)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(spare)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    _flush_system_dns()
    return True


class LeaseGuard:
    """Решает, пора ли освобождать имена после непрерывной смерти шима."""

    def __init__(self, grace: float) -> None:
        self.grace = grace
        self.down_since: float | None = None

    def tick(self, alive: bool, now: float) -> bool:
        """Вернуть ``True``, когда процесса непрерывно нет не меньше ``grace`` секунд."""
        if alive:
            self.down_since = None
            return False
        if self.down_since is None:
            self.down_since = now
            return False
        return now - self.down_since >= self.grace


def _process_alive(path: str) -> bool:
    try:
        with open(path, encoding="ascii") as handle:
            pid = int(handle.read().strip())
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


def guard_lease(pidfile: str, grace: float, names: list[str], hosts: str = _HOSTS) -> None:
    """Держать аренду сквозь короткий рестарт, но снять после настоящей смерти шима."""
    guard = LeaseGuard(grace)
    while True:
        if guard.tick(_process_alive(pidfile), time.monotonic()):
            set_pins(hosts, [], names)
        time.sleep(_LEASE_POLL)


def load_probes(path: str) -> dict[str, tuple[str, str]]:
    """Чем щупать источники: строки ``имя|путь|тело`` от установки (её список `SHIMS`)."""
    out: dict[str, tuple[str, str]] = {}
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                host, _, rest = line.strip().partition("|")
                probe, _, body = rest.partition("|")
                if host and probe:
                    out[host.lower()] = (probe, body)
    except OSError:
        pass
    return out


def load_pages(path: str) -> dict[str, int]:
    """Кому постраничный обход и какого размера страница: строки ``имя|N`` от установки."""
    out: dict[str, int] = {}
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                host, _, size = line.strip().partition("|")
                if host and size.isdigit() and int(size) > 0:
                    out[host.lower()] = int(size)
    except OSError:
        pass
    return out


def _page_bodies(route: Route, body: bytes | None) -> list[tuple[int, bytes]] | None:
    """Разложить запрос на страницы: ``(сколько строк просим, тело)`` на каждую.

    ``None`` - запрос уходит как есть: маршруту постраничный обход не включён, тела
    нет, это не JSON со ``size``/``from``, или строк и так не больше страницы.
    Тело - список раздач, который клиент просил ОДНИМ ответом; мы просим его частями,
    потому что канал рвёт ответ по объёму (TC-696), а мелкие проходят.
    """
    if route.page <= 0 or body is None:
        return None
    try:
        payload = json.loads(body)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    size, base = payload.get("size"), payload.get("from", 0)
    if not isinstance(size, int) or not isinstance(base, int) or size <= route.page:
        return None
    out: list[tuple[int, bytes]] = []
    last = base + size
    while base < last:
        ask = min(route.page, last - base)
        chunk = dict(payload, **{"from": base, "size": ask})
        out.append((ask, json.dumps(chunk).encode()))
        base += ask
    return out


def probe_direct(host: str, path: str, body: str, address: str) -> bool:
    """Отвечает ли имя ЦЕЛИКОМ, если идти к нему НАПРЯМУЮ, мимо `/etc/hosts`.

    Та же проба, которой судит установка (`probe_whole` в install.sh) и тем же самым
    curl: судья - ПРОСТОЙ потока (`--speed-time`/`--speed-limit`, TC-235), а не часы,
    потому что болезнь выглядит как «заголовки пришли, тело встало», а не как «долго».
    Отличий два, и оба обязательны. Первое: адрес подставляем свой (`--resolve`) - имя в
    `/etc/hosts` прибито к нам же, и обычная проба ушла бы сквозь шим и всегда отвечала
    бы «всё хорошо» (ровно поэтому прежний код и не пересматривал решение). Второе: тело
    читается целиком, потому что рвётся оно на объёме, и проба на один коннект больного
    имени не видит.
    """
    timeout = os.environ.get("TORRCAST_PROBE_TIMEOUT") or _PROBE_TIMEOUT
    stall = os.environ.get("TORRCAST_PROBE_STALL") or _PROBE_STALL
    floor = os.environ.get("TORRCAST_PROBE_FLOOR") or _PROBE_FLOOR
    agent = os.environ.get("TORRCAST_PROBE_UA") or _PROBE_UA
    command = [
        "curl", "-fsS",
        "-m", timeout,
        "--speed-time", stall,
        "--speed-limit", floor,
        "-o", os.devnull,
        "-A", agent,
        "--resolve", f"{host}:443:{f'[{address}]' if ':' in address else address}",
    ]  # fmt: skip
    if body:
        command += ["-H", "Content-Type: application/json", "-X", "POST", "-d", body]
    command.append(f"https://{host}{path}")
    try:
        # Список аргументов, а не строка: оболочки в этом пути нет вовсе.
        done = subprocess.run(command, capture_output=True, timeout=float(timeout) + 5, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


class Watch(threading.Thread):
    """Перерешает, идти ли к имени напрямую или через шим, и правит `/etc/hosts`.

    🔴 TC-260. Решение принималось один раз при установке и жило вечно, а канал живёт
    иначе: замер живьём - в 19:00 имя рвалось в 100% попыток, в 20:00 в 0% на обоих его
    адресах. Значит, решение обязано иметь срок годности и переигрываться по факту, а не
    по памяти об установке.

    Перекос сознательный и держится на цене ошибки. Лишний обход здорового имени стоит
    почти ничего (лишний местный хоп), а пропущенный обход больного - молчащего индексера
    до следующей установки. Поэтому: одна неудачная проба сразу возвращает имя за шим, а
    снимается обход только после :data:`_WATCH_CLEAR` удачных подряд. Проверить не вышло
    (DNS молчит) - решение не меняем вовсе, а счёт удачных обнуляем.

    На горячем пути этого нет и быть не может: живёт в своём потоке, ходит по кругу раз в
    :data:`_WATCH_EVERY` секунд и щупает источники ПО ОДНОМУ - параллельные пробы к
    трекеру и есть то, чем зарабатывается многочасовой бан индексера.
    """

    def __init__(
        self,
        routes: dict[str, Route],
        resolver: Resolver,
        pinned: Iterable[str],
        hosts: str = _HOSTS,
        every: float = _WATCH_EVERY,
        probe: Callable[[str, str, str, str], bool] = probe_direct,
    ) -> None:
        super().__init__(daemon=True, name="route-watch")
        self.routes = routes
        self.resolver = resolver
        self.hosts = hosts
        self.every = every
        self.pinned = {h.lower() for h in pinned}
        self._probe = probe
        self._good: dict[str, int] = dict.fromkeys(routes, 0)

    def apply(self) -> bool:
        """Привести `/etc/hosts` к нынешнему решению."""
        return set_pins(self.hosts, sorted(self.pinned), self.routes)

    def verdict(self, route: Route) -> bool | None:
        """Отвечает ли имя напрямую: ``None`` - проверить не вышло.

        Здоровье требует согласия ВСЕХ адресов, на которые может лечь клиент: он
        выбирает дорогу сам, и один больной край - это молчащий индексер через раз.
        """
        try:
            found = self.resolver.client_addresses(route.host)
        except OSError:
            return None
        if not found:
            return None
        return all(self._probe(route.host, route.path, route.body, at) for at in found)

    def round(self) -> None:
        """Один круг проверок: по одному имени за раз, потом одна правка файла."""
        for host, route in self.routes.items():
            if not route.path:
                continue
            healthy = self.verdict(route)
            if healthy is None:
                self._good[host] = 0
                continue
            if not healthy:
                self._good[host] = 0
                if host not in self.pinned:
                    self.pinned.add(host)
                    print(f"{host}: имя режется, веду через шим", file=sys.stderr, flush=True)
                continue
            self._good[host] += 1
            if self._good[host] >= _WATCH_CLEAR and host in self.pinned:
                self.pinned.discard(host)
                print(f"{host}: отвечает по имени, обход снят", file=sys.stderr, flush=True)
        self.apply()

    def run(self) -> None:
        while True:
            time.sleep(self.every)
            with contextlib.suppress(Exception):  # круг проверок не вправе ронять шим
                self.round()


def _plain_context() -> ssl.SSLContext:
    """Контекст без проверки имени: у origin'а, спрошенного по IP, серт на другое имя."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Переходы отдаём вызывающему: он вернётся к нам же по прибитому имени."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def _opener(verify: bool) -> urllib.request.OpenerDirector:
    context = ssl.create_default_context() if verify else _plain_context()
    return urllib.request.build_opener(_NoRedirect(), urllib.request.HTTPSHandler(context=context))


def _pinned_opener(address: str) -> urllib.request.OpenerDirector:
    """Опенер, который жмёт на ЗАДАННЫЙ адрес, а имя берёт из адресной строки.

    Ровно то, чего не умеет `getaddrinfo`: имя в `/etc/hosts` прибито к самому шиму, и
    обычный запрос вернулся бы к нам же. Подменяем только адрес соединения - SNI, `Host`
    и проверка серта остаются на настоящем имени (`https://yts.gg/...` при соединении на
    адрес его origin'а).
    """
    context = ssl.create_default_context()

    class Connection(http.client.HTTPSConnection):
        def connect(self) -> None:
            self.sock = context.wrap_socket(
                socket.create_connection((address, self.port), self.timeout),
                server_hostname=self.host,
            )

    class Handler(urllib.request.HTTPSHandler):
        def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
            return self.do_open(Connection, req)

    return urllib.request.build_opener(_NoRedirect(), Handler())


def _unpack(
    payload: bytes, headers: list[tuple[str, str]], wanted: bool
) -> tuple[bytes, list[tuple[str, str]]]:
    """Распаковать тело, если наверху взяли сжатым, а клиент сжатого не просил.

    Сжатие тут - наша самодеятельность (см. модульную строку), клиент о нём не знает, и
    отдать ему gzip, которого он не просил, значило бы сломать разбор ответа. Не
    распаковалось - отдаём как есть вместе с заголовком: пусть лучше клиент увидит
    сжатое тело и скажет об этом, чем получит мусор под видом целого ответа.
    """
    encoding = ""
    for name, value in headers:
        if name.lower() == "content-encoding":
            encoding = value.strip().lower()
    if wanted or encoding != "gzip" or not payload:
        return payload, headers
    try:
        body = gzip.decompress(payload)
    except (OSError, EOFError, zlib.error):
        return payload, headers
    return body, [(n, v) for n, v in headers if n.lower() != "content-encoding"]


def _client_present(conn: socket.socket) -> bool:
    """Клиент ещё на линии - или оборвал соединение, пока стоял в очереди?

    Подсматриваем в приёмный буфер, ничего не вычитывая. Здоровый клиент ждёт ответа и
    молчит - буфер пуст, ``select`` его не показывает, считаем живым. Если же сокет читаем,
    заглядываем одним байтом с ``MSG_PEEK`` (не потребляя его): пусто - пришёл EOF, сторона
    закрылась; что-то есть - клиент на месте. ``MSG_PEEK`` на TLS-сокете нельзя, поэтому
    смотрим сырой TCP через отдельную ручку того же сокета; менять режим самого сокета
    нельзя - флаг блокировки у дубля общий с оригиналом.
    """
    try:
        readable, _, _ = select.select([conn], [], [], 0)
    except OSError:
        return False
    if not readable:
        return True
    try:
        raw = socket.socket(conn.family, socket.SOCK_STREAM, fileno=os.dup(conn.fileno()))
    except OSError:
        return False
    try:
        return raw.recv(1, socket.MSG_PEEK) != b""
    except OSError:
        return False
    finally:
        raw.close()


@contextlib.contextmanager
def _in_queue(
    route: Route,
    conn: socket.socket,
    present: Callable[[socket.socket], bool] = _client_present,
) -> Iterator[bool]:
    """Занять место в очереди к хосту; ``True`` - слот наш, идём на хост.

    Свободно - проходим сразу, ничего не стоит. Занято - ждём здесь, а не идём на хост
    третьими. Личный таймаут запроса ожидание не съедает: он отсчитывается уже за
    воротами, так что медленный сосед по очереди не превращается в отказ.

    Осознанного потолка на ожидание живого клиента нет: оборвать его своим 504 нельзя,
    потому что Prowlarr читает такой ответ как отказ источника. Но очередь проверяет
    соединение короткими интервалами, чтобы уже ушедший клиент не ждал освобождения слота.

    Дождавшийся слота проверяет, жив ли ещё клиент: тот мог оборвать соединение, пока
    стоял в очереди. Такой слот тратить на поход к хосту и запись в мёртвый сокет незачем -
    отпускаем сразу, и следующий в очереди проходит по-настоящему. Проверка живости -
    довод: у сервера она боевая, у его испытания - подставная.
    """
    if route.gate.acquire(blocking=False):
        try:
            yield True
        finally:
            route.gate.release()
        return
    waited = time.monotonic()
    while not route.gate.acquire(timeout=_QUEUE_POLL):
        if not present(conn):
            waited = time.monotonic() - waited
            print(
                f"{route.host}: клиент ушёл из очереди через {waited:.1f} с",
                file=sys.stderr,
                flush=True,
            )
            yield False
            return
    waited = time.monotonic() - waited
    print(f"{route.host}: очередь, ждал {waited:.1f} с", file=sys.stderr, flush=True)
    if not present(conn):
        route.gate.release()
        print(f"{route.host}: клиент ушёл из очереди, слот свободен", file=sys.stderr, flush=True)
        yield False
        return
    try:
        yield True
    finally:
        route.gate.release()


def _activated_socket() -> socket.socket | None:
    """Забрать слушающий fd systemd; без socket activation вернуть ``None``."""
    if os.environ.get("LISTEN_PID") != str(os.getpid()) or os.environ.get("LISTEN_FDS") != "1":
        return None
    return socket.socket(fileno=3)


def build_server(
    cert: str,
    key: str,
    port: int,
    routes: dict[str, Route],
    resolver: Resolver | None = None,
    *,
    timeout: float = _TIMEOUT,
    route_timeout: float = _ROUTE_TIMEOUT,
    opener: Callable[[bool], urllib.request.OpenerDirector] = _opener,
    present: Callable[[socket.socket], bool] = _client_present,
    host: str = "127.0.0.1",
) -> http.server.HTTPServer:
    """Собрать слушающий шим.

    Отдельно от :func:`main` - чтобы его можно было завести на случайном порту и
    остановить: так его гоняют тесты. Разбор имён общий с :class:`Watch` - у обоих одна
    и та же память об адресах origin'ов.

    Ручки поведения - доводы, а не модульные переменные: сроки похода наверх, фабрика
    опенеров и проверка живости клиента называются здесь, и тест подставляет свои
    именно сюда, не переписывая модуль задним числом.
    """
    # Отдельным именем, а не переприсваиванием: замыкание обработчика видит его как
    # уже разрешённый, без «а вдруг там None».
    names: Resolver = resolver or Resolver()
    openers = {True: opener(True), False: opener(False)}
    #: Опенеры кандидата `named`: по одному на адрес, собираются на первом же походе.
    pinned: dict[str, urllib.request.OpenerDirector] = {}
    pinned_lock = threading.Lock()
    handshakes: dict[object, str] = {}
    handshakes_lock = threading.Lock()

    def opener_for(target: Target) -> urllib.request.OpenerDirector:
        if not target.via:
            return openers[target.verify]
        with pinned_lock:
            return pinned.setdefault(target.via, _pinned_opener(target.via))

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: object) -> None:
            """В journald и так всё видно, а запросы светить незачем."""

        def _route(self) -> Route | None:
            host = (self.headers.get("Host") or "").split(":")[0].lower()
            return routes.get(host)

        def _reply(self, status: int, headers: list[tuple[str, str]], data: bytes) -> None:
            self.send_response(status)
            for name, value in headers:
                if name.lower() not in _HOP:
                    self.send_header(name, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _forward(self, method: str) -> None:
            route = self._route()
            if route is None:
                self._reply(421, [("Content-Type", "text/plain")], b"host not routed here\n")
                return
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            # Тело от клиента читаем до очереди: место занимаем ровно на поход к хосту.
            with _in_queue(route, self.connection, present) as ours:
                if ours:
                    self._upstream(route, method, body)

        def _upstream(self, route: Route, method: str, body: bytes | None) -> None:
            pages = _page_bodies(route, body) if method == "POST" else None
            if pages is not None:
                self._paged_upstream(route, pages)
                return
            last = "маршрут пуст"
            deadline = time.monotonic() + route_timeout
            #: Придержанный 5xx: ответ, который лучше не отдавать, пока есть непробованный
            #: кандидат. Отдадим его, только если лучше не нашлось.
            held: tuple[int, list[tuple[str, str]], bytes] | None = None
            wanted = "gzip" in (self.headers.get("Accept-Encoding") or "").lower()
            for target in route.targets(names):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    last = "маршрут не ответил в срок"
                    break
                request = urllib.request.Request(target.base + self.path, data=body, method=method)
                request.add_header("Host", route.host)
                for name, value in self.headers.items():
                    if name.lower() not in _HOP:
                        request.add_header(name, value)
                # Просим сжатие ПОСЛЕ клиентских заголовков: своё «gzip» здесь важнее
                # того, что прислал клиент, а вниз тело всё равно поедет распакованным.
                request.add_header("Accept-Encoding", "gzip")
                try:
                    with opener_for(target).open(
                        request, timeout=min(timeout, remaining)
                    ) as response:
                        route.current = target.number
                        payload, headers = _unpack(
                            response.read(), list(response.headers.items()), wanted
                        )
                        self._reply(response.status, headers, payload)
                        return
                except urllib.error.HTTPError as exc:  # ответ есть, просто не 2xx
                    payload, headers = _unpack(exc.read(), list(exc.headers.items()), wanted)
                    if exc.code < 500:  # это ответ трекера по существу: «нет», «нельзя»
                        route.current = target.number
                        self._reply(exc.code, headers, payload)
                        return
                    # 🔴 TC-237. Пятисотый - не ответ, а его отсутствие, и отдавать его,
                    # имея непробованного кандидата, нельзя: Prowlarr читает ЛЮБОЙ 5xx как
                    # «повтори» и сам ретраит с отсрочкой (в его логе «Request for … failed
                    # with status BadGateway. Retrying in 0.26-4.19 s»). Снять этот повтор
                    # настройкой нечем - строка зашита в его сборку, - зато повод для него
                    # чаще всего наш: запасной адрес у нас уже есть, просто до него не
                    # доходило. Сбойный кандидат вдобавок не запоминается: пометить его
                    # «сработавшим» значило бы начинать с него и в следующий раз.
                    held = held or (exc.code, headers, payload)
                    last = f"{target.base}: {exc.code} {exc.reason}"
                except Exception as exc:  # любой отказ значит «следующий кандидат»
                    last = f"{target.base}: {exc}"
            if held is not None:  # лучше не нашлось - отдаём чужой отказ как есть
                status, headers, payload = held
                self._reply(status, headers, payload)
                return
            self._reply(502, [("Content-Type", "text/plain")], f"{last}\n".encode())

        def _paged_upstream(self, route: Route, pages: list[tuple[int, bytes]]) -> None:
            """Выдача по страницам: каждая едет каналом сама, клиенту - одна склейка.

            🔴 TC-696. Правила перебора те же, что у одиночного похода
            (:meth:`_upstream`), но граница смены кандидата другая: уйти на следующий
            адрес можно, только пока не доехала ПЕРВАЯ страница - у соседа выдача может
            лежать в другом порядке, и его страницы не продолжение начатых, а другая
            выдача. Оборвалась середина - отдаём собранное: часть каталога честнее,
            чем повод к повтору, которым Prowlarr зарабатывает индексеру бан. Страницы
            строго по одной: параллельный веер - это то, за что трекер банит.
            """
            last = "маршрут пуст"
            deadline = time.monotonic() + route_timeout
            held: tuple[int, list[tuple[str, str]], bytes] | None = None
            wanted = "gzip" in (self.headers.get("Accept-Encoding") or "").lower()
            for target in route.targets(names):
                merged: dict[str, Any] | None = None
                headers: list[tuple[str, str]] = []
                for want, page_body in pages:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        last = "маршрут не ответил в срок"
                        break
                    request = urllib.request.Request(
                        target.base + self.path, data=page_body, method="POST"
                    )
                    request.add_header("Host", route.host)
                    for name, value in self.headers.items():
                        if name.lower() not in _HOP:
                            request.add_header(name, value)
                    # Сжатие просим так же, как в одиночном походе: мелкая страница
                    # сжатой ещё дальше от порога обрыва.
                    request.add_header("Accept-Encoding", "gzip")
                    try:
                        with opener_for(target).open(
                            request, timeout=min(timeout, remaining)
                        ) as response:
                            # Склеивать можно только распакованное, поэтому страницы
                            # распаковываем всегда, чего бы ни просил клиент.
                            payload, page_headers = _unpack(
                                response.read(), list(response.headers.items()), False
                            )
                            page = json.loads(payload)
                            hits = page.get("hits") if isinstance(page, dict) else None
                            if not isinstance(hits, list):
                                raise ValueError("в ответе нет списка hits")
                            if merged is None:
                                route.current = target.number
                                merged, headers = page, page_headers
                                merged["hits"] = []
                            merged["hits"] += hits
                            if len(hits) < want:  # каталог кончился раньше страницы
                                break
                    except urllib.error.HTTPError as exc:
                        if merged is not None:  # середина цепочки: отдаём собранное
                            print(
                                f"{route.host}: страница не доехала ({exc.code}), "
                                f"отдаю собранные {len(merged['hits'])} строк",
                                file=sys.stderr,
                                flush=True,
                            )
                            break
                        payload, exc_headers = _unpack(
                            exc.read(), list(exc.headers.items()), wanted
                        )
                        if exc.code < 500:  # ответ по существу - как в одиночном походе
                            route.current = target.number
                            self._reply(exc.code, exc_headers, payload)
                            return
                        held = held or (exc.code, exc_headers, payload)
                        last = f"{target.base}: {exc.code} {exc.reason}"
                        break
                    except Exception as exc:  # обрыв страницы: как выше
                        if merged is not None:
                            print(
                                f"{route.host}: страница оборвалась ({exc}), "
                                f"отдаю собранные {len(merged['hits'])} строк",
                                file=sys.stderr,
                                flush=True,
                            )
                            break
                        last = f"{target.base}: {exc}"
                        break
                if merged is None:  # первая страница не доехала - следующий кандидат
                    continue
                out = json.dumps(merged).encode()
                if wanted:  # клиент сам просил сжатие - упакуем склейку обратно
                    out = gzip.compress(out)
                    headers.append(("Content-Encoding", "gzip"))
                self._reply(200, headers, out)
                return
            if held is not None:  # лучше не нашлось - отдаём чужой отказ как есть
                status, headers, payload = held
                self._reply(status, headers, payload)
                return
            self._reply(502, [("Content-Type", "text/plain")], f"{last}\n".encode())

        def do_GET(self) -> None:
            self._forward("GET")

        def do_HEAD(self) -> None:
            self._forward("HEAD")

        def do_POST(self) -> None:
            self._forward("POST")

    class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
        request_queue_size = _BACKLOG
        address_family = socket.AF_INET6 if ":" in host else socket.AF_INET

        def get_request(self) -> tuple[socket.socket, Any]:
            """Принять соединение и НЕ здороваться: рукопожатие - дело потока.

            🔴 TC-306. Обёрнутый слушающий сокет здоровается прямо в приёмном цикле:
            :meth:`ssl.SSLSocket.accept` доводит рукопожатие до конца и только потом
            возвращает соединение. Пока оно идёт, шим не принимает НИКОГО - а таймаута
            у слушающего сокета нет, так что клиент, поднявший TCP и замолчавший
            (канал съел его ClientHello - ровно та болезнь, ради которой шим и живёт),
            вешает не себя, а весь шим. Замер на живой машине: ОДИН такой молчун - и
            все сто следующих запросов ушли в таймаут, вместо ответа 421 за доли
            секунды. Очередь приёма тут не спасает никакая: она копится, а не тает.

            Поэтому обёртка уехала в :meth:`finish_request`, то есть в поток запроса:
            приёмный цикл теперь только принимает. Заодно у рукопожатия появился срок
            (:data:`_HANDSHAKE`) - молчун стоит одного потока и десяти секунд.
            """
            conn, addr = self.socket.accept()
            conn.settimeout(_HANDSHAKE)
            return conn, addr

        def finish_request(self, request: Any, client_address: Any) -> None:
            """Рукопожатие и сам запрос - уже своим потоком (см. :meth:`get_request`)."""
            tls = context.wrap_socket(request, server_side=True)
            with handshakes_lock:
                handshakes.pop(client_address, None)
            # Сроку место было ровно на рукопожатии: дальше запрос живёт по своим
            # часам (:data:`_TIMEOUT` наверх) и по терпению клиента, как и раньше.
            tls.settimeout(None)
            try:
                super().finish_request(tls, client_address)
            finally:
                # Сокет теперь наш: `wrap_socket` забрал у исходного его дескриптор,
                # и закрыть исходный (это сделает socketserver) уже ничего не закроет.
                self.shutdown_request(tls)

        def handle_error(
            self, request: socket.socket | tuple[bytes, socket.socket], client_address: object
        ) -> None:
            """Клиент, ушедший раньше ответа - одна строка, а не трейсбек.

            Штатное событие: Prowlarr закрыл соединение до того, как шим записал
            ответ, и ``wfile.write`` падает ``ssl.SSLEOFError``. Сорок строк трейсбека
            на каждый такой уход выглядят в журнале аварией и топят настоящие поломки,
            поэтому обрыв клиента печатается одной строкой - как уход из очереди
            (:func:`_in_queue`). 🔴 Глушится ТОЛЬКО он: любое другое исключение идёт
            прежним трейсбеком - молчание о настоящей поломке хуже шума.

            Второй такой же случай - несостоявшееся рукопожатие (TC-306): молчун и
            мусор на порту теперь падают тут, а не в приёмном цикле. Это тоже про
            клиента, а не про нас, и трейсбека не стоит.
            """
            failed = sys.exc_info()[1]
            if isinstance(failed, (ssl.SSLEOFError, BrokenPipeError, ConnectionResetError)):
                print("клиент ушёл раньше ответа", file=sys.stderr, flush=True)
                return
            if isinstance(failed, (ssl.SSLError, TimeoutError)):
                with handshakes_lock:
                    host = handshakes.pop(client_address, "SNI absent")
                print(f"{host}: рукопожатие не состоялось: {failed}", file=sys.stderr, flush=True)
                return
            super().handle_error(request, client_address)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)

    def remember_sni(tls: Any, server_name: str | None, _context: Any) -> int | None:
        with handshakes_lock:
            handshakes[tls.getpeername()] = server_name or "SNI absent"
        return None

    context.set_servername_callback(remember_sni)
    # Слушающий сокет остаётся голым нарочно: обёртка на нём означала бы рукопожатие
    # в приёмном цикле (TC-306, см. `Server.get_request`). TLS надевается на каждое
    # принятое соединение отдельно, уже в его потоке.
    activated = _activated_socket()
    if activated is None or ":" in host:
        return Server((host, port), Handler)
    server = Server((host, port), Handler, bind_and_activate=False)
    server.socket.close()
    server.socket = activated
    server.server_address = activated.getsockname()
    server.server_name = "localhost"
    server.server_port = port
    return server


def main(argv: list[str] | None = None, *, build: Callable[..., Any] = build_server) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    # Окружение читается здесь, в точке входа, а не на импорте модуля: только так его
    # можно назвать доводом - прочитанное на импорте не подменить ни тесту, ни юниту,
    # поднятому с другими значениями.
    hosts = os.environ.get("TORRCAST_HOSTS") or _HOSTS
    # Две служебные ходки без сервера. `--resolve` - адрес origin'а мимо `/etc/hosts`:
    # им установка щупает источник напрямую, тем же приёмом, что и сам шим.
    if args and args[0] == "--resolve":
        found = 0
        resolver = Resolver()
        for host in args[1:]:
            with contextlib.suppress(OSError):
                print("\n".join(resolver.client_addresses(host)))
                found += 1
        return 0 if found else 1
    # `--unpin` - снять наши строки. Это же делает юнит после остановки службы, чтобы
    # имена не остались прибитыми к тому, кого больше нет (даже после SIGKILL).
    if args and args[0] == "--unpin":
        set_pins(hosts, [], args[1:])
        return 0
    if args and args[0] == "--guard":
        guard_lease(args[1], float(args[2]), args[3:], hosts)
        return 0

    cert, key, port_text = args[:3]
    probes = load_probes(os.environ.get("TORRCAST_ROUTE_PROBES") or "")
    pages = load_pages(os.environ.get("TORRCAST_ROUTE_PAGES") or "")
    routes: dict[str, Route] = {}
    for spec in args[3:]:
        name, _, candidates = spec.partition("=")
        path, body = probes.get(name.lower(), ("", ""))
        routes[name.lower()] = Route(
            name, [c for c in candidates.split(",") if c], path, body, pages.get(name.lower(), 0)
        )
    if not routes:
        print("нечего вести: не задан ни один маршрут имя=кандидат", file=sys.stderr)
        return 2
    resolver = Resolver()
    port = int(port_text)
    server = build(cert, key, port, routes, resolver)
    ipv6 = None
    if os.environ.get("TORRCAST_LISTEN_IPV6") == "1":
        ipv6 = build(cert, key, port, routes, resolver, host="::1")
    pidfile = os.environ.get("TORRCAST_SHIM_PID") or ""
    if pidfile:
        with open(pidfile, "w", encoding="ascii") as handle:
            handle.write(str(os.getpid()))
    pinned = (os.environ.get("TORRCAST_ROUTE_PINNED") or "").replace(",", " ").split()
    every = float(os.environ.get("TORRCAST_ROUTE_EVERY") or _WATCH_EVERY)
    watch = Watch(routes, resolver, pinned, hosts=hosts, every=every)
    # Прибиваем только теперь: сокет уже слушает, и ответить есть кому. Освобождает имена
    # отдельный сторож, если процесса непрерывно нет дольше штатного RestartSec.
    watch.apply()
    if watch.every > 0:
        watch.start()
    if ipv6 is not None:
        threading.Thread(target=ipv6.serve_forever, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        if ipv6 is not None:
            ipv6.shutdown()
            ipv6.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
