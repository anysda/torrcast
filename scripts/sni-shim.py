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

Кандидаты пробуются по порядку, сработавший запоминается до первой осечки. Осечка - это
не только оборванное соединение: ответ 5xx тоже уводит на следующего кандидата, потому
что это не ответ трекера, а его отсутствие, и клиент (Prowlarr) читает такой ответ как
«повтори» - повторяет сам, с отсрочкой и по тому же адресу. Пока у нас есть запасной
адрес, отдавать наверх повод для повтора незачем; кончились кандидаты - отдаём чужой
отказ как есть.

Прибитое имя - это АРЕНДА, а не запись навсегда. Строки в `/etc/hosts` ставит сам шим,
когда сокет уже слушает, и снимает их, уходя (и штатным `stop`, и падением: то же самое
делает `ExecStopPost=` юнита). Иначе шим был бы единой точкой отказа на все свои имена
сразу: пока строка висит, имя ведёт на 127.0.0.1, где никто не отвечает, и трекер
пропадает не «пока чинится обход», а насовсем. Без строки он идёт своим путём - хуже, чем
через шим, но это деградация, а не смерть каталога.

Решение «прямо или через шим» тоже не вечное: канал режет по имени не всегда, обрыв
приходит и уходит в пределах часа. Поэтому шим ПЕРЕРЕШАЕТ его фоном (:class:`Watch`),
щупая источник НАПРЯМУЮ, мимо `/etc/hosts` - проба сквозь себя же всегда отвечала бы
«всё хорошо». Цена ошибки несимметрична: лишний обход здорового имени не стоит почти
ничего, а пропущенный обход больного - это молчащий индексер до следующей установки.
Отсюда и перекос: на любом сомнении ведём через шим, а снимаем обход только после
нескольких проверок подряд, где имя ответило целиком.

Наверх шим всегда просит `gzip`, а вниз отдаёт распакованным, если клиент сжатого не
просил. Это не экономия трафика, а обход той же болезни: рвётся поток на ОБЪЁМЕ тела,
и сжатая выдача чаще остаётся ниже порога обрыва (замер на yts.gg: 60 КБ голого тела
обрываются на 15 КБ и висят до таймаута, те же данные в gzip - 4.8 КБ и целиком за
0.9 с). Prowlarr сжатия не просит (видно в pcap), и попросить его за Prowlarr больше
некому.

К одному хосту шим держит не больше двух запросов зараз: фронт трекера, спрошенный
по IP, столько и тянет, а лишним параллельным отвечает 504 на шестнадцатой секунде -
после серии таких индексер уезжает в бан на три часа. Лишние ждут очереди, а не летят
на хост. Счёт очереди у каждого хоста свой: больной сосед чужие не задерживает, и
одиночный запрос на пустой очереди не ждёт вовсе.

Слушает только 127.0.0.1; наружу не смотрит и ничего не кэширует.

    sni-shim.py <cert> <key> <порт> имя=кандидат[,кандидат…] …
    sni-shim.py --resolve имя …   адреса origin'а мимо `/etc/hosts` (ими щупает установка)
    sni-shim.py --unpin имя …     снять наши строки из `/etc/hosts` (это же делает юнит)

Остальное приезжает окружением, чтобы не городить кавычки в строке запуска юнита:
`TORRCAST_HOSTS`, `TORRCAST_ROUTE_PROBES` (файл `имя|путь|тело` - чем щупать),
`TORRCAST_ROUTE_PINNED` (что прибито на старте), `TORRCAST_ROUTE_EVERY` (как часто
перерешать, 0 - не перерешать) и пороги пробы `TORRCAST_PROBE_*` - те же, что у установки.
"""

from __future__ import annotations

import contextlib
import gzip
import http.client
import http.server
import os
import random
import select
import signal
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
from typing import TYPE_CHECKING, NamedTuple

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
_TIMEOUT = 30
#: Сколько запросов зараз пускаем на ОДИН хост. Два - потолок, который держит самый
#: слабый из наших фронтов; третий параллельный он уже не обслуживает, а роняет в 504.
_PER_HOST = 2
#: Насколько верим разобранному адресу origin'а, прежде чем спросить DNS заново.
_DNS_TTL = 300.0
_DNS_TIMEOUT = 5.0

#: Где лежит таблица имён. Подменяется в песочнице и в тестах.
_HOSTS = os.environ.get("TORRCAST_HOSTS") or "/etc/hosts"
#: Метка наших строк в ней: по ней и только по ней мы их потом убираем. Чужую строку
#: (например, нарочно прибитый каталог определений Prowlarr) не трогаем никогда.
_PIN_MARK = "# torrcast-shim"
#: Как часто перерешать маршрут. Ноль - не перерешать вовсе (так гоняют тесты).
_WATCH_EVERY = float(os.environ.get("TORRCAST_ROUTE_EVERY") or 900)
#: Сколько проверок ПОДРЯД имя должно ответить целиком, чтобы снять с него обход.
#: Больше одной нарочно: снять обход по одной удачной пробе - это как раз тот дешёвый
#: способ получить дорогую ошибку (молчащий индексер), от которого весь перекос и заведён.
_WATCH_CLEAR = 2
#: Пороги пробы - те же, что у установки (`probe_whole` в install.sh, TC-235): судим по
#: ПРОСТОЮ потока, а не по общему времени. Значения приезжают оттуда же, окружением.
_PROBE_TIMEOUT = os.environ.get("TORRCAST_PROBE_TIMEOUT") or "25"
_PROBE_STALL = os.environ.get("TORRCAST_PROBE_STALL") or "5"
_PROBE_FLOOR = os.environ.get("TORRCAST_PROBE_FLOOR") or "1024"
_PROBE_UA = os.environ.get("TORRCAST_PROBE_UA") or (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122 Safari/537.36"
)


def _nameservers() -> list[str]:
    """Адреса DNS из `/etc/resolv.conf` - только IPv4, только те, что там указаны."""
    out: list[str] = []
    try:
        with open("/etc/resolv.conf", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "nameserver" and ":" not in parts[1]:
                    out.append(parts[1])
    except OSError:
        pass
    return out


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

    def __init__(self, ttl: float = _DNS_TTL) -> None:
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
        for server in _nameservers():
            try:
                found = [a for a in _query(host, server) if not a.startswith("127.")]
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
        for server in _nameservers():
            try:
                sixth = [a for a in _query(host, server, 28) if ":" in a]
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

    def __init__(self, host: str, candidates: list[str], path: str = "", body: str = "") -> None:
        self.host = host
        self.candidates = candidates
        #: Чем щупать источник напрямую (:class:`Watch`): путь и тело POST. Пусто - имя
        #: перерешать нечем, и маршрут у него остаётся тот, с которым его завели.
        self.path = path
        self.body = body
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
    lines += [f"127.0.0.1 {host} {_PIN_MARK}" for host in wanted]
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
    return True


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
    command = [
        "curl", "-fsS",
        "-m", _PROBE_TIMEOUT,
        "--speed-time", _PROBE_STALL,
        "--speed-limit", _PROBE_FLOOR,
        "-o", os.devnull,
        "-A", _PROBE_UA,
        "--resolve", f"{host}:443:{f'[{address}]' if ':' in address else address}",
    ]  # fmt: skip
    if body:
        command += ["-H", "Content-Type: application/json", "-X", "POST", "-d", body]
    command.append(f"https://{host}{path}")
    try:
        # Список аргументов, а не строка: оболочки в этом пути нет вовсе.
        done = subprocess.run(
            command, capture_output=True, timeout=float(_PROBE_TIMEOUT) + 5, check=False
        )
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
def _in_queue(route: Route, conn: socket.socket) -> Iterator[bool]:
    """Занять место в очереди к хосту; ``True`` - слот наш, идём на хост.

    Свободно - проходим сразу, ничего не стоит. Занято - ждём здесь, а не идём на хост
    третьими. Личный таймаут запроса ожидание не съедает: он отсчитывается уже за
    воротами, так что медленный сосед по очереди не превращается в отказ.

    Осознанного потолка на само ожидание нет, и это не упущение. Ждущих на хост не больше,
    чем мест (``_PER_HOST``), так что верхняя граница ожидания конечна - порядка одного
    таймаута на место впереди - и клиент со своим таймаутом всё равно сдаётся раньше. А
    оборвать ожидание своим 504 нельзя: 504 от нас Prowlarr читает так же, как 504 от
    перегруженного хоста, и уводит индексер в тот самый многочасовой бан, ради ухода от
    которого весь потолок и заведён. Ожидание тут строго безопаснее отказа.

    Дождавшийся слота проверяет, жив ли ещё клиент: тот мог оборвать соединение, пока
    стоял в очереди. Такой слот тратить на поход к хосту и запись в мёртвый сокет незачем -
    отпускаем сразу, и следующий в очереди проходит по-настоящему.
    """
    if route.gate.acquire(blocking=False):
        try:
            yield True
        finally:
            route.gate.release()
        return
    waited = time.monotonic()
    route.gate.acquire()
    waited = time.monotonic() - waited
    print(f"{route.host}: очередь, ждал {waited:.1f} с", file=sys.stderr, flush=True)
    if not _client_present(conn):
        route.gate.release()
        print(f"{route.host}: клиент ушёл из очереди, слот свободен", file=sys.stderr, flush=True)
        yield False
        return
    try:
        yield True
    finally:
        route.gate.release()


def build_server(
    cert: str, key: str, port: int, routes: dict[str, Route], resolver: Resolver | None = None
) -> http.server.HTTPServer:
    """Собрать слушающий шим.

    Отдельно от :func:`main` - чтобы его можно было завести на случайном порту и
    остановить: так его гоняют тесты. Разбор имён общий с :class:`Watch` - у обоих одна
    и та же память об адресах origin'ов.
    """
    resolver = resolver or Resolver()
    openers = {True: _opener(verify=True), False: _opener(verify=False)}
    #: Опенеры кандидата `named`: по одному на адрес, собираются на первом же походе.
    pinned: dict[str, urllib.request.OpenerDirector] = {}
    pinned_lock = threading.Lock()

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
            with _in_queue(route, self.connection) as ours:
                if ours:
                    self._upstream(route, method, body)

        def _upstream(self, route: Route, method: str, body: bytes | None) -> None:
            last = "маршрут пуст"
            #: Придержанный 5xx: ответ, который лучше не отдавать, пока есть непробованный
            #: кандидат. Отдадим его, только если лучше не нашлось.
            held: tuple[int, list[tuple[str, str]], bytes] | None = None
            wanted = "gzip" in (self.headers.get("Accept-Encoding") or "").lower()
            for target in route.targets(resolver):
                request = urllib.request.Request(target.base + self.path, data=body, method=method)
                request.add_header("Host", route.host)
                for name, value in self.headers.items():
                    if name.lower() not in _HOP:
                        request.add_header(name, value)
                # Просим сжатие ПОСЛЕ клиентских заголовков: своё «gzip» здесь важнее
                # того, что прислал клиент, а вниз тело всё равно поедет распакованным.
                request.add_header("Accept-Encoding", "gzip")
                try:
                    with opener_for(target).open(request, timeout=_TIMEOUT) as response:
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

        def do_GET(self) -> None:
            self._forward("GET")

        def do_HEAD(self) -> None:
            self._forward("HEAD")

        def do_POST(self) -> None:
            self._forward("POST")

    class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True

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
            """
            if isinstance(
                sys.exc_info()[1], (ssl.SSLEOFError, BrokenPipeError, ConnectionResetError)
            ):
                print("клиент ушёл раньше ответа", file=sys.stderr, flush=True)
                return
            super().handle_error(request, client_address)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server = Server(("127.0.0.1", port), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    return server


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
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
        set_pins(_HOSTS, [], args[1:])
        return 0

    cert, key, port_text = args[:3]
    probes = load_probes(os.environ.get("TORRCAST_ROUTE_PROBES") or "")
    routes: dict[str, Route] = {}
    for spec in args[3:]:
        name, _, candidates = spec.partition("=")
        path, body = probes.get(name.lower(), ("", ""))
        routes[name.lower()] = Route(name, [c for c in candidates.split(",") if c], path, body)
    if not routes:
        print("нечего вести: не задан ни один маршрут имя=кандидат", file=sys.stderr)
        return 2
    resolver = Resolver()
    server = build_server(cert, key, int(port_text), routes, resolver)
    pinned = (os.environ.get("TORRCAST_ROUTE_PINNED") or "").replace(",", " ").split()
    watch = Watch(routes, resolver, pinned, hosts=_HOSTS, every=_WATCH_EVERY)
    # Уходя, снимаем свои строки: имя, прибитое к молчащему шиму, - это не «обход не
    # работает», а «трекера нет». Поэтому и SIGTERM ловим сами - иначе сюда не вернуться.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        watch.apply()  # прибиваем только теперь: сокет уже слушает, и ответить есть кому
        if watch.every > 0:
            watch.start()
        server.serve_forever()
    finally:
        set_pins(watch.hosts, [], routes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
