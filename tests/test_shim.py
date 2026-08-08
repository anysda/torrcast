"""Шим для трекеров, чьё имя не проходит по TLS (``scripts/sni-shim.py``).

Проверяется здесь ровно одно, зато замером, а не рассуждением: сколько запросов шим
пускает на хост одновременно. Фронт трекера, спрошенный по IP, тянет два; третьему
параллельному он отвечает 504 на шестнадцатой секунде, а после серии таких Prowlarr
уводит индексер в бан на три часа. Поэтому лишние обязаны ЖДАТЬ.

Бэкенд здесь свой, медленный и считающий: он сам говорит, сколько запросов держал
зараз. Сети тесту не нужно.
"""

from __future__ import annotations

import http.server
import importlib.util
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

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
