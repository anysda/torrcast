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
"""

from __future__ import annotations

import contextlib
import gzip
import http.client
import http.server
import os
import random
import select
import socket
import socketserver
import ssl
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
import zlib
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Iterator

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


def _query_a(host: str, server: str) -> list[str]:
    """Спросить у DNS адреса имени напрямую, минуя `/etc/hosts`.

    Через `socket.getaddrinfo` нельзя: имя там уже прибито к нам же, и шим ходил бы
    сам к себе. Запрос простой - один вопрос об A-записи, ответ разбираем руками.
    """
    ident = random.randrange(1 << 16)  # не крипта: ident отсеивает чужие ответы
    labels = b"".join(bytes([len(p)]) + p for p in host.encode("idna").split(b"."))
    query = struct.pack(">HHHHHH", ident, 0x0100, 1, 0, 0, 0) + labels + b"\0"
    query += struct.pack(">HH", 1, 1)
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
        rtype, _cls, _ttl, rdlen = struct.unpack(">HHIH", data[pos : pos + 10])
        pos += 10
        if rtype == 1 and rdlen == 4:
            out.append(socket.inet_ntoa(data[pos : pos + 4]))
        pos += rdlen
    return out


class Resolver:
    """Адреса origin'ов: спрашиваем DNS сами и держим разобранное недолгое время."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, list[str]]] = {}
        self._lock = threading.Lock()

    def addresses(self, host: str) -> list[str]:
        with self._lock:
            fresh = self._cache.get(host)
            if fresh and fresh[0] > time.monotonic():
                return fresh[1]
        found: list[str] = []
        for server in _nameservers():
            try:
                found = [a for a in _query_a(host, server) if not a.startswith("127.")]
            except (OSError, struct.error, IndexError):
                continue
            if found:
                break
        if not found:
            raise OSError(f"DNS не дал адреса для {host}")
        with self._lock:
            self._cache[host] = (time.monotonic() + _DNS_TTL, found)
        return found


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

    def __init__(self, host: str, candidates: list[str]) -> None:
        self.host = host
        self.candidates = candidates
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
            if candidate not in ("direct", "named"):
                out.append(Target(candidate.rstrip("/"), True, "", number))
                continue
            try:
                found = resolver.addresses(self.host)
            except OSError:
                continue
            if candidate == "direct":  # по адресу и без имени: серт там на чужое имя
                out += [Target(f"https://{ip}", False, "", number) for ip in found]
            else:  # по адресу, но с именем: и SNI, и серт остаются настоящими
                out += [Target(f"https://{self.host}", True, ip, number) for ip in found]
        return out


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
    cert: str, key: str, port: int, routes: dict[str, Route]
) -> http.server.HTTPServer:
    """Собрать слушающий шим.

    Отдельно от :func:`main` - чтобы его можно было завести на случайном порту и
    остановить: так его гоняют тесты.
    """
    resolver = Resolver()
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


def main() -> int:
    cert, key, port_text = sys.argv[1:4]
    routes: dict[str, Route] = {}
    for spec in sys.argv[4:]:
        name, _, candidates = spec.partition("=")
        routes[name.lower()] = Route(name, [c for c in candidates.split(",") if c])
    if not routes:
        print("нечего вести: не задан ни один маршрут имя=кандидат", file=sys.stderr)
        return 2
    build_server(cert, key, int(port_text), routes).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
