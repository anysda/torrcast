"""Проверяет устройство HTTPS-клиента Wikimedia без обращения в сеть."""

from __future__ import annotations

import http.server
import socket
import ssl
import threading
import time
from typing import Any, ClassVar

import pytest

from tests import thread_guard
from tests.conftest import free_port
from torrcast.adapters.wiki.http_json_client import HttpJsonClient, _IPv4Connection
from torrcast.domain.facts.settings import FACTS_BUDGET


def test_keeps_user_agent() -> None:
    """Клиент хранит переданное имя автоматики для каждого запроса."""
    assert HttpJsonClient("torrcast/test").user_agent == "torrcast/test"


def test_a_memoized_address_rides_over_a_dns_storm() -> None:
    """Разрешённый адрес переживает DNS-бурю мимо резолвера, а голый резолв в ней тонет.

    ``socket.getaddrinfo`` таймауту сокета не подчиняется: под бурей параллельных
    резолвов прогрева он залипает дольше всего бюджета справки, и та не приезжает вовсе.
    Буря смоделирована блокирующим резолвером (``blocked`` не взведён - резолв не
    возвращается). Прямой резолв в ней не укладывается в бюджет, а память клиента и его
    собственный таймаут - укладываются.
    """
    blocked = threading.Event()

    def stuck(host: str, *_a: Any, **_k: Any) -> Any:
        blocked.wait()  # под бурей резолвер не отвечает
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 0))]

    client = HttpJsonClient("torrcast/test", stuck)

    # Память переживает бурю: адрес разрешили ОДНАЖДЫ, до бури.
    blocked.set()
    assert client._resolve("wiki.example", 1.0) == "1.2.3.4"
    blocked.clear()  # буря снова накрыла резолвер
    started = time.monotonic()
    assert client._resolve("wiki.example", 1.5) == "1.2.3.4"
    assert time.monotonic() - started < FACTS_BUDGET, "из памяти - мимо бури, в срок"

    # Холодный резолв под бурей не ест весь бюджет, а падает по своему сроку. Отказ
    # отдаётся не мгновенно: сперва клиент закрывает за собой поднятую нитку
    # (закрытие), и в буре это ожидание выбирается целиком - потолок у него общий с
    # меню: дольше, чем всё меню согласно ждать справку, закрытие не длится.
    started = time.monotonic()
    try:
        client._resolve("cold.example", 0.5)
    except OSError:
        pass
    else:
        raise AssertionError("холодный резолв под бурей обязан упасть по таймауту")
    spent = time.monotonic() - started
    assert 0.5 <= spent < 0.5 + FACTS_BUDGET + 0.5, "уложился в срок и закрытие, а не завис"

    # А вот голый резолв (прежнее поведение connect) в той же буре в срок не отвечает.
    done = threading.Event()

    def bare_resolve() -> None:
        stuck("nomemo.example")
        done.set()

    threading.Thread(target=bare_resolve, daemon=True).start()
    assert not done.wait(FACTS_BUDGET), "прямой резолв под бурей за бюджет не разрешился"

    blocked.set()  # отпустить залипших демонов


def test_a_refusal_by_deadline_takes_its_resolver_thread_with_it() -> None:
    """🔴 TC-722. Отказ по сроку уносит с собой нитку, которую сам же и поднял.

    Разрешению имени срок даёт отдельная нитка: ``getaddrinfo`` таймауту не подчиняется.
    Брошенная на произвол, она доживает своё уже в чужой работе - в бою это показ, в
    прогоне соседняя проба, и красным там оказывается невиновный. Мера тут не «сколько
    ждали», а «что осталось живым»: её и спрашивает сторож (:mod:`tests.thread_guard`).

    Резолвер тут отвечает, но много позже срока. Отказ по сроку остаётся отказом - зато
    опоздавший ответ ложится в память, и следующий спросивший берёт его даром. Без этого
    каждый запрос к молчащему имени заводил свою нитку и бросал её.
    """
    late = threading.Event()

    def slow(host: str, *_a: Any, **_k: Any) -> Any:
        late.wait(1.0)  # резолвер отвечает, но много позже отведённого срока
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 0))]

    client = HttpJsonClient("torrcast/test", slow)
    before = thread_guard.alive()
    started = time.monotonic()
    with pytest.raises(OSError):
        client._resolve("late.example", 0.05)

    left = thread_guard.alive() - before
    assert not left, f"нитку закрыл тот, кто её поднял, а живой осталась {left}"
    assert time.monotonic() - started >= 1.0, "отказ отдан после закрытия, а не вместо него"
    assert client._resolve("late.example", 0.05) == "1.2.3.4", "опоздавший ответ не пропал"


def test_warming_a_name_asks_for_it_once_and_does_not_wait_for_the_answer() -> None:
    """🔴 TC-957. Греть - значит спросить имя заранее и сразу вернуться, а не ждать адрес.

    Ждать тут нечего: адрес понадобится второй волне справки, а до неё ещё целая первая.
    Второй нитки на то же имя греющий не поднимает - и уже известное имя не спрашивает
    заново: иначе каждое согревание стоило бы своей нитки.
    """
    asked: list[str] = []
    slow = threading.Event()

    def creeping(host: str) -> list[Any]:
        asked.append(host)
        slow.wait(5.0)
        return [(0, 0, 0, "", ("1.2.3.4", 0))]

    client = HttpJsonClient("проба", lookup=creeping)
    started = time.monotonic()
    client.warm("en.wikipedia.org")
    client.warm("en.wikipedia.org")
    spent = time.monotonic() - started

    try:
        assert spent < 0.5, f"согревание не ждёт ответа, а оно просидело {spent:.2f} с"
        assert asked == ["en.wikipedia.org"], "одна нитка на имя, сколько его ни грей"
    finally:
        slow.set()


class _Store(http.server.BaseHTTPRequestHandler):
    """Склад картинок на одну пробу: отдаёт постер и помнит, кем назвался спросивший."""

    poster: ClassVar[bytes] = b""
    seen: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        _Store.seen.append(self.headers.get("User-Agent", ""))
        if self.path != "/poster.jpg":
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(_Store.poster)))
        self.end_headers()
        self.wfile.write(_Store.poster)

    def log_message(self, fmt: str, *args: Any) -> None:
        return None


@pytest.mark.machine
def test_a_picture_is_fetched_over_real_tls_and_by_ipv4(
    tls: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Настоящая раздача, настоящий TLS: картинка приезжает байтами, а имя - своё.

    Постер тянет СЕРВ, а не карточка (:data:`hass.posters.ROUTE`), и тянет он его тем же
    клиентом, что и справку: та же память адресов, тот же проверенный TLS и тот же
    именной ``User-Agent`` - без него Wikimedia отвечает 429 уже на втором запросе подряд.
    Проверяется это на своей раздаче, а не на Wikimedia: чужой хост в прогоне мерил бы
    доступность Wikimedia, а не клиента.
    """
    _Store.poster = b"\xff\xd8\xff\xe0" + b"picture" * 100
    _Store.seen = []
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(tls[0], tls[1])
    server = http.server.ThreadingHTTPServer(("127.0.0.1", free_port()), _Store)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True, name="store").start()
    monkeypatch.setattr(_IPv4Connection, "context", ssl.create_default_context(cafile=tls[0]))
    client = HttpJsonClient(
        "torrcast/test",
        lambda host: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))],
    )
    port = server.server_address[1]
    try:
        assert client.fetch(f"https://127.0.0.1:{port}/poster.jpg", 10.0) == _Store.poster
        assert _Store.seen == ["torrcast/test"], f"склад увидел {_Store.seen}"

        with pytest.raises(OSError, match="404"):
            client.fetch(f"https://127.0.0.1:{port}/no-such.jpg", 10.0)
    finally:
        server.shutdown()
        server.server_close()
