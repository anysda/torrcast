"""Проверяет устройство HTTPS-клиента Wikimedia без обращения в сеть."""

from __future__ import annotations

import socket
import threading
import time
from typing import Any

import pytest

from tests import thread_guard
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
