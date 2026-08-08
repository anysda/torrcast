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

Кандидаты пробуются по порядку, сработавший запоминается до первой осечки.

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
import http.server
import random
import socket
import socketserver
import ssl
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

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


class Route:
    """Один трекер: имя, которое видит Prowlarr, и кандидаты, куда ходить на самом деле."""

    def __init__(self, host: str, candidates: list[str]) -> None:
        self.host = host
        self.candidates = candidates
        self.current = 0
        #: Места в очереди к ЭТОМУ хосту. Свой счётчик на каждый - в этом весь смысл:
        #: хост, который сейчас болеет, держит только своих ждущих.
        self.gate = threading.BoundedSemaphore(_PER_HOST)

    def targets(self, resolver: Resolver) -> list[tuple[str, bool, int]]:
        """Куда идти: ``(база, проверять ли серт, номер кандидата)``, с рабочего."""
        order = list(range(len(self.candidates)))
        order = order[self.current :] + order[: self.current]
        out: list[tuple[str, bool, int]] = []
        for number in order:
            candidate = self.candidates[number]
            if candidate != "direct":
                out.append((candidate.rstrip("/"), True, number))
                continue
            try:
                out += [(f"https://{ip}", False, number) for ip in resolver.addresses(self.host)]
            except OSError:
                continue
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


@contextlib.contextmanager
def _in_queue(route: Route) -> Iterator[None]:
    """Занять место в очереди к хосту.

    Свободно - проходим сразу, ничего не стоит. Занято - ждём здесь, а не идём на хост
    третьими. Личный таймаут запроса ожидание не съедает: он отсчитывается уже за
    воротами, так что медленный сосед по очереди не превращается в отказ.
    """
    if not route.gate.acquire(blocking=False):
        waited = time.monotonic()
        route.gate.acquire()
        waited = time.monotonic() - waited
        print(f"{route.host}: очередь, ждал {waited:.1f} с", file=sys.stderr, flush=True)
    try:
        yield
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
            with _in_queue(route):
                self._upstream(route, method, body)

        def _upstream(self, route: Route, method: str, body: bytes | None) -> None:
            last = "маршрут пуст"
            for base, verify, number in route.targets(resolver):
                request = urllib.request.Request(base + self.path, data=body, method=method)
                request.add_header("Host", route.host)
                for name, value in self.headers.items():
                    if name.lower() not in _HOP:
                        request.add_header(name, value)
                try:
                    with openers[verify].open(request, timeout=_TIMEOUT) as response:
                        route.current = number
                        payload = response.read()
                        self._reply(response.status, list(response.headers.items()), payload)
                        return
                except urllib.error.HTTPError as exc:  # ответ есть, просто не 2xx
                    route.current = number
                    self._reply(exc.code, list(exc.headers.items()), exc.read())
                    return
                except Exception as exc:  # любой отказ значит «следующий кандидат»
                    last = f"{base}: {exc}"
            self._reply(502, [("Content-Type", "text/plain")], f"{last}\n".encode())

        def do_GET(self) -> None:
            self._forward("GET")

        def do_HEAD(self) -> None:
            self._forward("HEAD")

        def do_POST(self) -> None:
            self._forward("POST")

    class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True

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
