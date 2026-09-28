"""Проверяет память IPv4-адресов: срок у резолвера свой, нитка одна на имя."""

from __future__ import annotations

import socket
import threading
import time
from typing import Any

import pytest

from tests import thread_guard
from torrcast.adapters.wiki.address_memory import AddressMemory
from torrcast.domain.facts.settings import FACTS_BUDGET


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

    client = AddressMemory(stuck)

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

    client = AddressMemory(slow)
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

    client = AddressMemory(lookup=creeping)
    started = time.monotonic()
    client.warm("en.wikipedia.org")
    client.warm("en.wikipedia.org")
    spent = time.monotonic() - started

    try:
        assert spent < 0.5, f"согревание не ждёт ответа, а оно просидело {spent:.2f} с"
        assert asked == ["en.wikipedia.org"], "одна нитка на имя, сколько его ни грей"
    finally:
        slow.set()


def test_a_lookup_lost_on_the_wire_gets_one_spare() -> None:
    """A lost resolver answer costs about the spare delay, not the resolver's own retry."""
    asked: list[str] = []
    lost = threading.Event()

    def flaky(host: str) -> list[Any]:
        asked.append(host)
        if len(asked) == 1:
            lost.wait(5.0)  # the first answer went missing: the resolver sits out its retry
        return [(0, 0, 0, "", ("1.2.3.4", 0))]

    client = AddressMemory(lookup=flaky)
    started = time.monotonic()
    try:
        assert client._resolve("m.example", 8.0) == "1.2.3.4"
        assert time.monotonic() - started < 2.0, "the lookup sat out the lost answer"
        assert len(asked) == 2
        client._resolved.clear()  # the address aged out while the lost lookup still hangs
        assert client._resolve("m.example", 8.0) == "1.2.3.4"
    finally:
        lost.set()


@pytest.mark.machine
def test_a_silent_name_never_gets_a_third_lookup() -> None:
    """Two askers of one silent name share its lookup and its single spare."""
    asked: list[str] = []
    silent = threading.Event()

    def mute(host: str) -> list[Any]:
        asked.append(host)
        silent.wait(5.0)
        return []

    client = AddressMemory(lookup=mute)
    threading.Timer(1.6, silent.set).start()
    refused: list[str] = []

    def ask() -> None:
        try:
            client._resolve("q.example", 1.3)
        except OSError as refusal:
            refused.append(str(refusal))

    askers = [threading.Thread(target=ask) for _ in range(2)]
    for one in askers:
        one.start()
    for one in askers:
        one.join(10.0)
    assert len(refused) == 2
    assert len(asked) == 2, f"one lookup and one spare per silent name, asked {asked}"
