"""Шим для трекеров, чьё имя не проходит по TLS (``scripts/sni-shim.py``).

Проверяется здесь замером, а не рассуждением, ровно два его свойства.

Первое: сколько запросов шим пускает на хост одновременно. Фронт трекера, спрошенный
по IP, тянет два; третьему параллельному он отвечает 504 на шестнадцатой секунде, а
после серии таких Prowlarr уводит индексер в бан на три часа. Поэтому лишние обязаны
ЖДАТЬ.

Второе: шим просит наверху gzip и отдаёт вниз распакованным (TC-213). Канал рвёт поток
на ОБЪЁМЕ тела, и сжатая выдача чаще остаётся ниже порога обрыва; Prowlarr сжатия не
просит, попросить за него больше некому.

Бэкенд здесь свой, медленный и считающий: он сам говорит, сколько запросов держал
зараз и о чём его просили. Сети тесту не нужно.
"""

from __future__ import annotations

import gzip
import http.server
import importlib.util
import socket
import ssl
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

#: Сколько держится один запрос на бэкенде. Заметно больше накладных расходов на TLS и
#: заметно меньше терпения теста.
HOLD = 0.4


def _load() -> ModuleType:
    """Шим - скрипт, а не модуль пакета: имя с дефисом обычным import не берётся."""
    path = Path(__file__).resolve().parent.parent / "scripts" / "sni-shim.py"
    spec = importlib.util.spec_from_file_location("sni_shim", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["sni_shim"] = module
    spec.loader.exec_module(module)
    return module


shim = _load()


class Counter:
    """Сколько запросов бэкенд держал одновременно - пик за всё время."""

    def __init__(self) -> None:
        self.now = 0
        self.peak = 0
        self.served = 0
        self._lock = threading.Lock()

    def enter(self) -> None:
        with self._lock:
            self.now += 1
            self.served += 1
            self.peak = max(self.peak, self.now)

    def leave(self) -> None:
        with self._lock:
            self.now -= 1


def _backend(tls: tuple[str, str], counter: Counter, hold: float = HOLD) -> http.server.HTTPServer:
    """Медленный origin: держит запрос ``hold`` секунд и считает, сколько их зараз."""

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: object) -> None:
            """Молчим: вывод теста не про это."""

        def do_GET(self) -> None:
            counter.enter()
            try:
                time.sleep(hold)
                body = b"ok\n"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            finally:
                counter.leave()

    class Server(http.server.ThreadingHTTPServer):
        daemon_threads = True

    cert, key = tls
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server = Server(("127.0.0.1", 0), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _get(port: int, host: str) -> tuple[int, float]:
    """Запрос к шиму под нужным именем в ``Host``: код ответа и сколько занял."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    request = urllib.request.Request(f"https://127.0.0.1:{port}/", headers={"Host": host})
    started = time.monotonic()
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))
    try:
        with opener.open(request, timeout=60) as response:
            response.read()
            return response.status, time.monotonic() - started
    except urllib.error.HTTPError as exc:  # ответ есть, просто не 2xx
        exc.read()
        return exc.code, time.monotonic() - started


@pytest.fixture
def plain_openers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Шим ходит к бэкенду по имени-кандидату, а серт там самоподписанный."""
    plain = shim._opener(verify=False)
    monkeypatch.setattr(shim, "_opener", lambda verify: plain)


@pytest.fixture
def backend(tls: tuple[str, str]) -> Iterator[tuple[http.server.HTTPServer, Counter]]:
    counter = Counter()
    server = _backend(tls, counter)
    yield server, counter
    server.shutdown()
    server.server_close()


def _shim(tls: tuple[str, str], routes: dict[str, object]) -> http.server.HTTPServer:
    cert, key = tls
    server: http.server.HTTPServer = shim.build_server(cert, key, 0, routes)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_two_at_a_time_on_the_host(
    tls: tuple[str, str],
    plain_openers: None,
    backend: tuple[http.server.HTTPServer, Counter],
) -> None:
    """Шесть одновременных запросов через шим - на хосте зараз не больше двух."""
    origin, counter = backend
    port = origin.server_address[1]
    routes = {"tracker.test": shim.Route("tracker.test", [f"https://127.0.0.1:{port}"])}
    server = _shim(tls, routes)
    try:
        front = server.server_address[1]
        with ThreadPoolExecutor(max_workers=6) as pool:
            flight = [pool.submit(_get, front, "tracker.test") for _ in range(6)]
            answers = [future.result() for future in flight]
    finally:
        server.shutdown()
        server.server_close()

    codes = [code for code, _ in answers]
    print(f"ответы: {codes}, обслужено бэкендом: {counter.served}, пик на бэкенде: {counter.peak}")
    assert codes == [200] * 6
    assert counter.served == 6, "запросы должны дойти все - очередь, а не отказ"
    assert counter.peak <= shim._PER_HOST, f"на хосте было {counter.peak} зараз"
    # Шесть запросов по два - три волны: очередь именно ждала, а не улетела веером.
    assert max(t for _, t in answers) >= HOLD * 2.5


def test_alone_does_not_wait(
    tls: tuple[str, str],
    plain_openers: None,
    backend: tuple[http.server.HTTPServer, Counter],
) -> None:
    """Одиночный запрос на пустом шиме не ждёт ничего: потолок ему не мешает."""
    origin, _ = backend
    port = origin.server_address[1]
    routes = {"tracker.test": shim.Route("tracker.test", [f"https://127.0.0.1:{port}"])}
    server = _shim(tls, routes)
    try:
        code, spent = _get(server.server_address[1], "tracker.test")
    finally:
        server.shutdown()
        server.server_close()
    print(f"одиночный: код {code}, {spent:.2f} с при выдержке бэкенда {HOLD} с")
    assert code == 200
    assert spent < HOLD * 2, "одиночный запрос стоял в очереди, а не должен был"


def test_queue_is_per_host(
    tls: tuple[str, str],
    plain_openers: None,
    backend: tuple[http.server.HTTPServer, Counter],
) -> None:
    """Очередь у каждого хоста своя: забитый сосед чужие запросы не задерживает.

    Больной хост здесь - тот, что не отвечает вовсе: два запроса к нему занимают его
    очередь целиком и висят до таймаута. Здоровый обязан ответить своим чередом.
    """
    origin, _ = backend
    port = origin.server_address[1]
    # Порт 1 на петле никто не слушает: соединение не встаёт, запрос стоит до таймаута.
    routes = {
        "sick.test": shim.Route("sick.test", ["https://127.0.0.1:1"]),
        "well.test": shim.Route("well.test", [f"https://127.0.0.1:{port}"]),
    }
    server = _shim(tls, routes)
    front = server.server_address[1]
    try:
        with ThreadPoolExecutor(max_workers=5) as pool:
            sick = [pool.submit(_get, front, "sick.test") for _ in range(3)]
            time.sleep(0.2)  # даём больному занять свою очередь целиком
            well = pool.submit(_get, front, "well.test")
            code, spent = well.result(timeout=20)
            for future in sick:
                future.cancel()
    finally:
        server.shutdown()
        server.server_close()
    print(f"здоровый хост при забитом соседе: код {code}, {spent:.2f} с")
    assert code == 200
    assert spent < HOLD * 3, "здоровый хост ждал чужую очередь"


def test_silent_candidate_does_not_hide_working_fallback(
    tls: tuple[str, str],
    plain_openers: None,
    backend: tuple[http.server.HTTPServer, Counter],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Первый молчун отдаёт место сменной альтернативе внутри бюджета маршрута."""
    monkeypatch.setattr(shim, "_TIMEOUT", 0.6)
    monkeypatch.setattr(shim, "_ROUTE_TIMEOUT", 1.5)
    blackhole = _blackhole()
    origin, counter = backend
    route = shim.Route(
        "tracker.test",
        [
            f"https://127.0.0.1:{blackhole.getsockname()[1]}",
            f"https://127.0.0.1:{origin.server_address[1]}",
        ],
    )
    server = _shim(tls, {"tracker.test": route})
    try:
        code, spent = _get(server.server_address[1], "tracker.test")
    finally:
        server.shutdown()
        server.server_close()
        blackhole.close()
    print(f"после молчуна: код {code}, {spent:.2f} с, фолбэк спросили {counter.served} раз")
    assert code == 200
    assert counter.served == 1
    assert spent < shim._ROUTE_TIMEOUT


def test_all_rutor_candidates_fit_indexer_budget() -> None:
    """Три способа доступа успевают сменить друг друга до потолка индексера."""
    assert shim._TIMEOUT * 3 <= shim._ROUTE_TIMEOUT < 20


#: Тело, на котором видно сжатие: повторяющийся текст ужимается в разы, и «просил ли шим
#: gzip» читается уже по размеру ответа, а не только по заголовку.
BULK = ("раздача matrix 1080p\n" * 400).encode()


class Asked:
    """Что бэкенд услышал в запросе и что отдал в ответ."""

    def __init__(self) -> None:
        self.encoding = ""
        self.sent_gzip = False


def _gzip_backend(tls: tuple[str, str], asked: Asked) -> http.server.HTTPServer:
    """Origin, который умеет отдавать сжатым - и запоминает, просили ли его об этом."""

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: object) -> None:
            """Молчим: вывод теста не про это."""

        def do_GET(self) -> None:
            asked.encoding = self.headers.get("Accept-Encoding") or ""
            body, packed = BULK, "gzip" in asked.encoding.lower()
            if packed:
                body = gzip.compress(BULK)
            asked.sent_gzip = packed
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            if packed:
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    class Server(http.server.ThreadingHTTPServer):
        daemon_threads = True

    cert, key = tls
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server = Server(("127.0.0.1", 0), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _fetch(port: int, host: str, accept: str | None = None) -> tuple[bytes, dict[str, str]]:
    """Запрос к шиму: тело ответа как есть и его заголовки."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    headers = {"Host": host} | ({"Accept-Encoding": accept} if accept else {})
    request = urllib.request.Request(f"https://127.0.0.1:{port}/", headers=headers)
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))
    with opener.open(request, timeout=30) as response:
        return response.read(), {k.lower(): v for k, v in response.headers.items()}


def test_shim_asks_gzip_and_unpacks_it(tls: tuple[str, str], plain_openers: None) -> None:
    """🔴 TC-213: клиент про сжатие не заикался - шим всё равно просит его наверху.

    Ради этого всё и затевалось: тело едет по каналу сжатым (тут - втрое короче), а
    клиент получает его распакованным и без ``Content-Encoding`` - для него не
    изменилось ничего.
    """
    asked = Asked()
    origin = _gzip_backend(tls, asked)
    routes = {
        "tracker.test": shim.Route(
            "tracker.test", [f"https://127.0.0.1:{origin.server_address[1]}"]
        )
    }
    server = _shim(tls, routes)
    try:
        body, headers = _fetch(server.server_address[1], "tracker.test")
    finally:
        server.shutdown()
        server.server_close()
        origin.shutdown()
        origin.server_close()
    print(
        f"наверх просили «{asked.encoding}», по каналу ехало {len(gzip.compress(BULK))} Б "
        f"вместо {len(BULK)} Б, клиенту приехало {len(body)} Б"
    )
    assert "gzip" in asked.encoding.lower(), "шим обязан просить сжатие за клиента"
    assert asked.sent_gzip, "origin отдал сжатым"
    assert body == BULK, "клиенту тело обязано приехать распакованным"
    assert "content-encoding" not in headers, "распаковали - заголовок обязан уйти"
    assert headers["content-length"] == str(len(BULK))


def test_client_that_asked_gzip_gets_it_as_is(tls: tuple[str, str], plain_openers: None) -> None:
    """А если сжатие просил сам клиент - отдаём как есть: распаковывать за него нечего."""
    asked = Asked()
    origin = _gzip_backend(tls, asked)
    routes = {
        "tracker.test": shim.Route(
            "tracker.test", [f"https://127.0.0.1:{origin.server_address[1]}"]
        )
    }
    server = _shim(tls, routes)
    try:
        body, headers = _fetch(server.server_address[1], "tracker.test", accept="gzip")
    finally:
        server.shutdown()
        server.server_close()
        origin.shutdown()
        origin.server_close()
    assert headers.get("content-encoding") == "gzip"
    assert gzip.decompress(body) == BULK


def test_named_candidate_keeps_the_name_and_pins_the_address() -> None:
    """Кандидат ``named``: адрес свой, имя настоящее.

    Без имени в рукопожатии CDN отвечает 403 (замер на yts.gg), а спросить имя обычным
    способом нельзя - в ``/etc/hosts`` оно прибито к самому шиму. Поэтому адрес берётся
    своим запросом к DNS, а в ``base`` остаётся имя: оно и уедет в SNI, и попадёт в
    проверку серта. Для сравнения ``direct`` - ровно наоборот.
    """

    class _Fixed:
        def addresses(self, host: str) -> list[str]:
            return ["203.0.113.7", "203.0.113.8"]

    resolver = _Fixed()
    named = shim.Route("tracker.test", ["named"]).targets(resolver)
    assert [(t.base, t.verify, t.via) for t in named] == [
        ("https://tracker.test", True, "203.0.113.7"),
        ("https://tracker.test", True, "203.0.113.8"),
    ]
    direct = shim.Route("tracker.test", ["direct"]).targets(resolver)
    assert [(t.base, t.verify, t.via) for t in direct] == [
        ("https://203.0.113.7", False, ""),
        ("https://203.0.113.8", False, ""),
    ]


class Hits:
    """Сколько раз спросили этот origin."""

    def __init__(self) -> None:
        self.count = 0
        self._lock = threading.Lock()

    def add(self) -> None:
        with self._lock:
            self.count += 1


def _status_backend(
    tls: tuple[str, str], status: int, hits: Hits, body: bytes
) -> http.server.HTTPServer:
    """Origin, который всегда отвечает заданным кодом и считает, сколько раз его спросили."""

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: object) -> None:
            """Молчим: вывод теста не про это."""

        def do_GET(self) -> None:
            hits.add()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    class Server(http.server.ThreadingHTTPServer):
        daemon_threads = True

    cert, key = tls
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server = Server(("127.0.0.1", 0), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_пятисотый_уводит_на_следующего_кандидата(
    tls: tuple[str, str], plain_openers: None
) -> None:
    """🔴 TC-237: 502 от первого адреса не уезжает наверх, пока есть второй.

    Prowlarr читает любой 5xx как «повтори» и повторяет сам, с отсрочкой и по тому же
    адресу; снять этот повтор настройкой нечем. Зато запасной адрес у нас уже есть -
    и пока он не спрошен, повода для повтора наверх отдавать нельзя. Заодно проверяем,
    что сбойный кандидат не запомнился: второй запрос идёт сразу к здоровому.
    """
    sick_hits, well_hits = Hits(), Hits()
    sick = _status_backend(tls, 502, sick_hits, b"bad gateway\n")
    well = _status_backend(tls, 200, well_hits, b'{"hits": []}\n')
    route = shim.Route(
        "tracker.test",
        [
            f"https://127.0.0.1:{sick.server_address[1]}",
            f"https://127.0.0.1:{well.server_address[1]}",
        ],
    )
    server = _shim(tls, {"tracker.test": route})
    try:
        first, _ = _get(server.server_address[1], "tracker.test")
        second, _ = _get(server.server_address[1], "tracker.test")
    finally:
        for srv in (server, sick, well):
            srv.shutdown()
            srv.server_close()
    print(f"коды: {first} и {second}; больного спросили {sick_hits.count} раз(а)")
    assert first == 200, "502 от первого кандидата обязан увести на второй"
    assert second == 200
    assert sick_hits.count == 1, "к сбойному кандидату второй раз не возвращаемся"
    assert well_hits.count == 2, "здоровый кандидат отвечает на оба запроса"


def test_чужой_отказ_доезжает_когда_кандидаты_кончились(
    tls: tuple[str, str], plain_openers: None
) -> None:
    """Все кандидаты отдали 5xx - наверх едет их код, а не выдуманный нами 502.

    И спрошены обязаны быть ВСЕ: отказ первого сам по себе ещё ничего не значит.
    """
    first_hits, second_hits = Hits(), Hits()
    one = _status_backend(tls, 503, first_hits, b"down\n")
    two = _status_backend(tls, 503, second_hits, b"down too\n")
    route = shim.Route(
        "tracker.test",
        [
            f"https://127.0.0.1:{one.server_address[1]}",
            f"https://127.0.0.1:{two.server_address[1]}",
        ],
    )
    server = _shim(tls, {"tracker.test": route})
    try:
        code, _ = _get(server.server_address[1], "tracker.test")
    finally:
        for srv in (server, one, two):
            srv.shutdown()
            srv.server_close()
    print(f"код наверх: {code}; спросили обоих: {first_hits.count} и {second_hits.count}")
    assert code == 503, "отдаём чужой отказ как есть, а не свой 502"
    assert first_hits.count == 1 and second_hits.count == 1, "спрошены обязаны быть все"


def _blackhole() -> socket.socket:
    """Хост, который принимает соединение и молчит: TLS-рукопожатие к нему висит.

    Занятый им слот освобождается только по таймауту - ровно так ведёт себя больной
    фронт, из-за которого весь потолок и заведён.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    held: list[socket.socket] = []

    def loop() -> None:
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            held.append(conn)  # держим и не отвечаем

    threading.Thread(target=loop, daemon=True).start()
    return srv


def _open_and_send(port: int, host: str) -> ssl.SSLSocket:
    """TLS-клиент к шиму: шлём запрос и НЕ читаем ответ - соединение остаётся у нас."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    conn = context.wrap_socket(socket.create_connection(("127.0.0.1", port)), server_hostname="x")
    conn.sendall(f"GET / HTTP/1.1\r\nHost: {host}\r\n\r\n".encode())
    return conn


def _drop_then_third(tls: tuple[str, str], sick_port: int) -> float:
    """Обрыв в очереди, затем настоящий третий запрос: за сколько тот получит ответ.

    Единственный слот держим руками - будто на хосте уже висит запрос. Первый клиент
    встаёт в очередь и обрывается, стоя в ней. Вторым в ту же очередь встаёт настоящий
    запрос через шим. Отпускаем ручной слот. Если обрыв замечен, оборвавшийся слот не
    занимает и третий уходит на хост сразу (один таймаут к больному). Если нет - мёртвый
    держит слот весь таймаут, и третий ждёт ещё столько же (два таймаута).
    """
    route = shim.Route("sick.test", [f"https://127.0.0.1:{sick_port}"])
    route.gate = threading.BoundedSemaphore(1)
    server = _shim(tls, {"sick.test": route})
    front = server.server_address[1]
    spent: dict[str, float] = {}

    def third() -> None:
        _code, took = _get(front, "sick.test")
        spent["took"] = took

    try:
        assert route.gate.acquire(blocking=False), "слот занять руками"
        dropped = _open_and_send(front, "sick.test")  # первый в очереди
        time.sleep(0.5)  # обработчик доходит до ожидания в очереди
        dropped.close()  # клиент бросает соединение, стоя в очереди
        time.sleep(0.2)  # FIN доезжает до шима
        worker = threading.Thread(target=third)
        worker.start()
        time.sleep(0.3)  # третий успевает встать в очередь вторым
        route.gate.release()  # ручной слот отпущен - очередь оживает
        worker.join(timeout=shim._TIMEOUT * 3 + 5)
        return spent["took"]
    finally:
        server.shutdown()
        server.server_close()


def test_dropped_client_frees_slot_at_once(
    tls: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Клиент, оборвавший соединение в очереди, слот не проедает: следующий проходит сразу.

    Замеряем оба поведения на одном сценарии. Со старым (проверку живости глушим) мёртвый
    держит слот весь таймаут к больному хосту, и третий ждёт два таймаута. С новым - обрыв
    замечен, слот сразу свободен, и третий укладывается в один таймаут.
    """
    monkeypatch.setattr(shim, "_TIMEOUT", 2)
    blackhole = _blackhole()
    sick_port = blackhole.getsockname()[1]
    try:
        with monkeypatch.context() as bypass:
            bypass.setattr(shim, "_client_present", lambda conn: True)
            stuck = _drop_then_third(tls, sick_port)
        freed = _drop_then_third(tls, sick_port)
    finally:
        blackhole.close()
    err = capsys.readouterr().err
    print(f"третий получил ответ: без проверки {stuck:.2f} с, с проверкой {freed:.2f} с")
    assert stuck >= shim._TIMEOUT * 1.8, "без проверки мёртвый держит слот весь таймаут"
    assert freed < shim._TIMEOUT * 1.7, "с проверкой третий укладывается в один таймаут"
    assert stuck - freed >= shim._TIMEOUT * 0.7, "проверка живости обязана вернуть слот раньше"
    assert "клиент ушёл из очереди" in err, "уход из очереди должен попасть в журнал"


def test_dropped_client_leaves_queue_before_a_slot_opens(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ушедший клиент не ждёт занятого origin до его многосекундного таймаута."""
    route = shim.Route("sick.test", ["direct"])
    poll = getattr(shim, "_QUEUE_POLL", 0.1)
    for _ in range(shim._PER_HOST):
        assert route.gate.acquire(blocking=False)
    client, peer = socket.socketpair()
    finished = threading.Event()

    def wait() -> None:
        with shim._in_queue(route, client) as ours:
            assert not ours
        finished.set()

    worker = threading.Thread(target=wait)
    worker.start()
    time.sleep(poll * 1.5)
    peer.close()
    try:
        assert finished.wait(poll * 4), "ушедший клиент остался в очереди"
        assert "клиент ушёл из очереди" in capsys.readouterr().err
    finally:
        for _ in range(shim._PER_HOST):
            route.gate.release()
        client.close()
        worker.join(timeout=1)


def _ask_briefly(port: int, host: str, budget: float = 8.0) -> tuple[int, float]:
    """Запрос к шиму с коротким терпением: код ответа и сколько ждали.

    Отдельно от :func:`_get` ровно из-за терпения: там минута, а здесь ответ либо
    приезжает за доли секунды, либо не приезжает вовсе, и ждать минуту незачем.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    began = time.monotonic()
    raw = socket.create_connection(("127.0.0.1", port), timeout=budget)
    raw.settimeout(budget)
    with context.wrap_socket(raw, server_hostname="x") as conn:
        conn.sendall(f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
        head = conn.recv(64).split(b"\r\n")[0].decode("ascii", "replace")
    return int(head.split()[1]), time.monotonic() - began


def test_молчащий_клиент_не_запирает_шим_целиком(
    tls: tuple[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-306. Клиент, поднявший TCP и замолчавший, стоит одного потока, а не всего шима.

    Так выглядит ровно та болезнь, ради которой шим и живёт: канал съел ClientHello, и
    соединение висит без единого байта. Пока рукопожатие делалось в приёмном цикле,
    такой молчун запирал приём НАСОВСЕМ - замер на живой машине: один молчун, и все сто
    следующих запросов ушли в таймаут вместо ответа за доли секунды.

    Проверяем самым дешёвым запросом, какой есть: имя не наше, ответ 421, до трекеров
    дело не доходит. Важно тут не что ответили, а что ответили вообще.
    """
    server = _shim(tls, {})
    port = server.server_address[1]
    quiet = socket.create_connection(("127.0.0.1", port), timeout=5)
    try:
        time.sleep(0.3)  # молчун успевает занять приёмный цикл, если тот его берёт
        code, took = _ask_briefly(port, "unknown.test")
        second, _ = _ask_briefly(port, "unknown.test")
    finally:
        quiet.close()
        server.shutdown()
        server.server_close()
    print(f"при молчуне ответ {code} за {took:.2f} с, следом {second}")
    assert code == 421, "запрос обязан быть обслужен, пока рядом висит молчун"
    assert second == 421, "и следующий тоже: молчун не занимает очередь навсегда"
    assert took < 3, "ответ не должен ждать чужого рукопожатия"
    assert server.request_queue_size > 5, "очередь приёма - не умолчание socketserver"
    assert "Traceback" not in capsys.readouterr().err, "молчун - не авария шима"


def _wait_log(capsys: pytest.CaptureFixture[str], marker: str, budget: float = 5.0) -> str:
    """Дождаться строки в журнале шима: печатает её поток обработчика, не мы."""
    deadline = time.monotonic() + budget
    err = ""
    while time.monotonic() < deadline:
        time.sleep(0.05)
        err = capsys.readouterr().err
        if marker in err or "Traceback" in err:
            break
    return err


def test_client_gone_before_the_answer_is_one_line_not_a_traceback(
    tls: tuple[str, str],
    plain_openers: None,
    backend: tuple[http.server.HTTPServer, Counter],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Клиент, ушедший раньше ответа - короткая строка в журнале, а не трейсбек.

    Штатная ситуация: Prowlarr закрыл соединение, пока шим ждал origin, и запись
    ответа в мёртвый сокет падает (``ssl.SSLEOFError`` и родня). Прежде каждый такой
    уход клал в журнал сорок строк трейсбека - штатное событие выглядело аварией и
    топило настоящие поломки.
    """
    origin, _ = backend
    port = origin.server_address[1]
    routes = {"tracker.test": shim.Route("tracker.test", [f"https://127.0.0.1:{port}"])}
    server = _shim(tls, routes)
    try:
        conn = _open_and_send(server.server_address[1], "tracker.test")
        # Обрыв с RST, а не вежливое закрытие: так запись ответа упадёт наверняка,
        # а не когда повезёт с буферами.
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        conn.close()  # клиент ушёл, не дожидаясь ответа
        err = _wait_log(capsys, "ушёл раньше ответа")
    finally:
        server.shutdown()
        server.server_close()
    print(f"журнал шима на ушедшего клиента: {err.strip()!r}")
    assert "ушёл раньше ответа" in err, "уход клиента обязан попасть в журнал строкой"
    assert "Traceback" not in err, "а трейсбека на штатное событие быть не должно"


def test_a_real_shim_failure_still_screams(
    tls: tuple[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    """Настоящая поломка обязана остаться трейсбеком: глушится только уход клиента.

    Молчание о поломке хуже шума: если «тишина» накрыла бы любое исключение, упавший
    шим выглядел бы здоровым. Здесь маршрут ломается сам - и журнал обязан об этом
    кричать, как кричал всегда.
    """

    class _Broken:
        host = "broken.test"
        gate = threading.BoundedSemaphore(shim._PER_HOST)
        current = 0

        def targets(self, resolver: object) -> list[object]:
            raise RuntimeError("настоящая поломка")

    server = _shim(tls, {"broken.test": _Broken()})
    try:
        with pytest.raises((urllib.error.URLError, OSError)):  # ответа нет - обрыв
            _get(server.server_address[1], "broken.test")
        err = _wait_log(capsys, "настоящая поломка")
    finally:
        server.shutdown()
        server.server_close()
    assert "Traceback" in err, "настоящая поломка обязана остаться трейсбеком"
    assert "настоящая поломка" in err, "и с её собственным текстом"
    assert "ушёл раньше ответа" not in err, "поломку нельзя принять за уход клиента"


# --- Маршрут не прибит навсегда: аренда имени и перерешение (TC-267, TC-260) ------


class _Steady:
    """Разбор имён, который всегда отвечает одним и тем же набором адресов."""

    def __init__(self, *addresses: str) -> None:
        self.list = list(addresses) or ["203.0.113.7"]

    def client_addresses(self, host: str) -> list[str]:
        return self.list


class _Mute:
    """Разбор имён, который не отвечает: проверить маршрут нечем."""

    def client_addresses(self, host: str) -> list[str]:
        raise OSError("DNS не дал адреса")


def _watch(
    hosts: Path,
    probe: object,
    pinned: tuple[str, ...] = (),
    resolver: object | None = None,
) -> Any:  # shim грузится importlib'ом, статического типа у него нет
    """Круг перепроверки с подставной пробой: сети тесту не нужно."""
    routes = {"tracker.test": shim.Route("tracker.test", ["direct"], "/search?q=matrix", "")}
    return shim.Watch(routes, resolver or _Steady(), pinned, hosts=str(hosts), every=0, probe=probe)


def test_the_name_is_leased_not_carved(tmp_path: Path) -> None:
    """Строку в hosts ставим и снимаем мы, а чужие строки в файле переживают это целыми.

    Сломай :func:`~sni_shim.set_pins` - и трекер либо останется прибитым к мёртвому шиму
    (то есть пропадёт совсем), либо утащит за собой чужую строку.
    """
    hosts = tmp_path / "hosts"
    hosts.write_text(
        "127.0.0.1 localhost\n"
        "127.0.0.1 indexers.prowlarr.com\n"  # чужая: прибита нарочно и не нами
        "127.0.0.1 tracker.test\n"  # наша, но прежняя - ещё без метки
        "192.0.2.10 nas.home\n",
        encoding="utf-8",
    )
    owned = ["tracker.test", "other.test"]

    assert shim.set_pins(str(hosts), ["other.test"], owned) is True
    lines = hosts.read_text(encoding="utf-8").splitlines()
    print(f"после аренды: {lines}")
    assert "127.0.0.1 other.test # torrcast-shim" in lines
    assert not any(line.startswith("127.0.0.1 tracker.test") for line in lines), (
        "имя, которое больше не ведём через шим, обязано перестать вести на 127.0.0.1"
    )
    assert "127.0.0.1 indexers.prowlarr.com" in lines, "чужую строку трогать нельзя"
    assert "192.0.2.10 nas.home" in lines
    assert shim.set_pins(str(hosts), ["other.test"], owned) is False, "повтор ничего не меняет"

    assert shim.set_pins(str(hosts), [], owned) is True
    left = hosts.read_text(encoding="utf-8").splitlines()
    print(f"после снятия: {left}")
    assert not any("torrcast-shim" in line for line in left)
    assert left == ["127.0.0.1 localhost", "127.0.0.1 indexers.prowlarr.com", "192.0.2.10 nas.home"]


def test_the_shim_hands_the_names_back_when_it_goes_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 TC-267. Шим упал - имена свободны; и прибиты они только пока сокет слушает.

    Это и есть вся разница между «обход не работает» и «трекера нет»: пока строка висит,
    имя ведёт на 127.0.0.1, где никого нет, и индексер пуст независимо от того, режет ли
    что-то канал прямо сейчас.
    """
    hosts = tmp_path / "hosts"
    hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
    monkeypatch.setattr(shim, "_HOSTS", str(hosts))
    monkeypatch.setattr(shim, "_WATCH_EVERY", 0.0)  # круг проверок тут не нужен
    monkeypatch.setenv("TORRCAST_ROUTE_PINNED", "tracker.test")
    monkeypatch.setenv("TORRCAST_ROUTE_PROBES", str(tmp_path / "нет-такого"))
    seen: list[list[str]] = []

    class _Listening:
        """Слушающий сокет: к этому мигу имя обязано быть уже прибито."""

        def serve_forever(self) -> None:
            seen.append(hosts.read_text(encoding="utf-8").splitlines())
            raise KeyboardInterrupt

    monkeypatch.setattr(shim, "build_server", lambda *a, **k: _Listening())
    with pytest.raises(KeyboardInterrupt):
        shim.main(["cert", "key", "0", "tracker.test=direct", "well.test=direct"])

    print(f"пока шим слушал: {seen[0]}")
    print(f"после его ухода: {hosts.read_text(encoding='utf-8').splitlines()}")
    assert "127.0.0.1 tracker.test # torrcast-shim" in seen[0], "прибивать надо уже на ходу"
    assert not any("well.test" in line for line in seen[0]), "здорового за шим не уводим"
    assert "127.0.0.1 tracker.test # torrcast-shim" in hosts.read_text(encoding="utf-8"), (
        "короткий штатный рестарт обязан сохранить аренду для следующего процесса"
    )


def test_lease_guard_ignores_restart_but_releases_a_dead_shim() -> None:
    """🔴 TC-323/TC-267. Короткий рестарт не отказ, долгая смерть освобождает hosts."""
    guard = shim.LeaseGuard(grace=12.0)
    verdicts = [
        guard.tick(False, 100.0),
        guard.tick(False, 105.0),  # штатный RestartSec
        guard.tick(True, 105.1),
        guard.tick(False, 200.0),
        guard.tick(False, 211.9),
        guard.tick(False, 212.0),
    ]
    print(f"решения сторожа: {verdicts}")
    assert verdicts == [False, False, False, False, False, True]


def test_shim_takes_the_systemd_socket_only_from_its_own_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Чужой activation env не трогаем; свой fd 3 переживает рестарт процесса."""
    seen: list[int] = []
    sentinel = object()
    monkeypatch.setenv("LISTEN_FDS", "1")
    monkeypatch.setenv("LISTEN_PID", "1")
    assert shim._activated_socket() is None
    monkeypatch.setenv("LISTEN_PID", str(shim.os.getpid()))

    def _remember(*_args: object, **kwargs: int) -> object:
        seen.append(kwargs["fileno"])
        return sentinel

    monkeypatch.setattr(shim.socket, "socket", _remember)
    assert shim._activated_socket() is sentinel
    assert seen == [3]


def test_one_dns_blip_does_not_empty_the_only_route(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 TC-267. У кого один кандидат, у того адрес и есть весь маршрут.

    Замер на живой машине: DNS не ответил пять секунд, и шим отдал `502 маршрут пуст`
    (пустой список целей - это ровно он) на nyaa и rutor разом, тогда как Knaben в тот же
    миг отвечал 200 своим запасным ИМЕНЕМ, которому адрес не нужен.
    """
    answers = [["203.0.113.7"]]

    def flaky(host: str, server: str, rtype: int = 1) -> list[str]:
        if not answers:
            raise OSError("DNS молчит")
        return answers.pop()

    monkeypatch.setattr(shim, "_nameservers", lambda: ["192.0.2.53"])
    monkeypatch.setattr(shim, "_query", flaky)
    resolver = shim.Resolver(ttl=0)  # свежесть тут не при чём: спрашиваем каждый раз
    route = shim.Route("tracker.test", ["direct"])

    first = [target.base for target in route.targets(resolver)]
    second = [target.base for target in route.targets(resolver)]
    print(f"при живом DNS: {first}; когда он замолчал: {second}")
    assert first == ["https://203.0.113.7"]
    assert second == first, "маршрут не вправе исчезать вместе с ответом DNS"


def test_a_mirror_is_a_second_address_for_the_same_catalogue() -> None:
    """🔴 TC-267. `direct:зеркало` - второй край того же каталога, а не другое имя.

    Имени в рукопожатии нет вовсе (идём по адресу), так что зеркало здесь - именно
    адрес; своё имя уезжает в `Host`, и трекер отвечает своей же выдачей.
    """

    class _TwoSided:
        def addresses(self, host: str) -> list[str]:
            return {"tracker.test": ["203.0.113.7"], "mirror.test": ["198.51.100.9"]}[host]

    route = shim.Route("tracker.test", ["direct", "direct:mirror.test"])
    targets = route.targets(_TwoSided())
    print(f"кандидаты по порядку: {[(t.base, t.verify) for t in targets]}")
    assert [t.base for t in targets] == ["https://203.0.113.7", "https://198.51.100.9"]
    assert not any(t.verify for t in targets), "по адресу серт всегда на чужое имя"


def test_a_cut_name_goes_back_behind_the_shim_at_once(tmp_path: Path) -> None:
    """🔴 TC-260. Имя начали резать - обход возвращается тем же кругом, без вопросов.

    Цена ошибки несимметрична: лишний обход здорового стоит местного хопа, а
    пропущенный обход больного - молчащего индексера до следующей установки. Поэтому
    сюда - сразу, а обратно - только с разбором (см. соседний тест).
    """
    hosts = tmp_path / "hosts"
    hosts.write_text("", encoding="utf-8")
    watch = _watch(hosts, probe=lambda *a: False)
    watch.round()
    lines = hosts.read_text(encoding="utf-8").splitlines()
    print(f"после круга: {lines}")
    assert lines == ["127.0.0.1 tracker.test # torrcast-shim"]


def test_the_bypass_is_lifted_only_after_a_run_of_clean_rounds(tmp_path: Path) -> None:
    """🔴 TC-260. Обход снимается по факту здоровья, но не по одной удачной пробе."""
    hosts = tmp_path / "hosts"
    hosts.write_text("", encoding="utf-8")
    watch = _watch(hosts, probe=lambda *a: True, pinned=("tracker.test",))
    watch.round()
    after_one = hosts.read_text(encoding="utf-8").splitlines()
    watch.round()
    after_two = hosts.read_text(encoding="utf-8").splitlines()
    print(f"после первого круга: {after_one}; после второго: {after_two}")
    assert after_one == ["127.0.0.1 tracker.test # torrcast-shim"], "одной пробы мало"
    assert after_two == [], "здоровое имя обязано вернуться на свой прямой путь"


def test_a_round_that_could_not_check_changes_nothing(tmp_path: Path) -> None:
    """Проверить не вышло (DNS молчит) - решение остаётся прежним, а счёт удачных обнуляется."""
    hosts = tmp_path / "hosts"
    hosts.write_text("", encoding="utf-8")
    watch = _watch(hosts, probe=lambda *a: True, pinned=("tracker.test",))
    watch.round()  # одна удачная проба уже была
    watch.resolver = _Mute()
    watch.round()  # проверить нечем - не считается
    watch.resolver = _Steady()
    watch.round()  # снова первая удачная
    print(f"после трёх кругов: {hosts.read_text(encoding='utf-8').splitlines()}")
    assert hosts.read_text(encoding="utf-8").splitlines() == [
        "127.0.0.1 tracker.test # torrcast-shim"
    ], "непроверенный круг не вправе ни снимать обход, ни считаться удачной пробой"


def test_a_name_is_healthy_only_when_every_family_answers(tmp_path: Path) -> None:
    """🔴 TC-260. Дорогу выбирает клиент, а не мы: один больной адрес - имя больное.

    Замер на живой машине: yts.gg по IPv4 отдавал ответ целиком за 0.3 с, и проба одного
    IPv4 честно говорила «здоров». Prowlarr в тот же миг брал IPv6 - обрыв тела на
    16401 Б и «Failed to read complete http response», то есть пустой индексер при
    зелёной пробе. Именно этот перекос и лечится согласием всех семейств.
    """
    hosts = tmp_path / "hosts"
    hosts.write_text("", encoding="utf-8")
    asked: list[str] = []

    def probe(host: str, path: str, body: str, address: str) -> bool:
        asked.append(address)
        return ":" not in address  # IPv6 режется, IPv4 отвечает целиком

    watch = _watch(
        hosts, probe=probe, resolver=_Steady("203.0.113.7", "2001:db8::7"), pinned=("tracker.test",)
    )
    watch.round()
    watch.round()
    print(f"щупали: {asked}; hosts: {hosts.read_text(encoding='utf-8').splitlines()}")
    assert "2001:db8::7" in asked, "IPv6 обязан быть прощупан: клиент берёт его первым"
    assert hosts.read_text(encoding="utf-8").splitlines() == [
        "127.0.0.1 tracker.test # torrcast-shim"
    ], "имя, больное хоть на одном семействе, обязано остаться за шимом"
