"""Проверяет устройство HTTPS-клиента Wikimedia без обращения в сеть."""

from __future__ import annotations

import socket
import threading
import time
from typing import Any

from torrcast.adapters.wiki.http_json_client import HttpJsonClient
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

    # Холодный резолв под бурей не ест весь бюджет, а падает по своему таймауту.
    started = time.monotonic()
    try:
        client._resolve("cold.example", 0.5)
    except OSError:
        pass
    else:
        raise AssertionError("холодный резолв под бурей обязан упасть по таймауту")
    assert 0.5 <= time.monotonic() - started < 1.2, "уложился в свой таймаут, а не завис"

    # А вот голый резолв (прежнее поведение connect) в той же буре в срок не отвечает.
    done = threading.Event()

    def bare_resolve() -> None:
        stuck("nomemo.example")
        done.set()

    threading.Thread(target=bare_resolve, daemon=True).start()
    assert not done.wait(FACTS_BUDGET), "прямой резолв под бурей за бюджет не разрешился"

    blocked.set()  # отпустить залипших демонов
