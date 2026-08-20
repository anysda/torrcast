"""Нитка одна на ключ, а не на запрос; держат её сроки справки."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Hashable
from typing import Generic, TypeVar

_Answer = TypeVar("_Answer")


class Lookers(Generic[_Answer]):
    """Нитки, поднятые по ключу: одна на ключ, и опоздавший ответ не пропадает.

    Срок у справки есть, а способа оборвать нитку, залипшую в системном вызове, в Python
    нет: срок отпускает СПРАШИВАЮЩЕГО, а нитка живёт дальше. Там, где по сроку отвечают
    человеку, платить закрытие некому - потолок ожидания справки продуктовый, и двигать
    его нельзя. Значит, лечится не длительность, а ЧИСЛО: пока нитка заводилась на каждый
    запрос, молчащий источник стоил по нитке за спрос, и все они доживали своё уже в
    показе. Нитка на ключ этого не умеет по построению.

    Второе следствие того же: опоздавший ответ достаётся следующему спросившему даром -
    его пишет сама нитка, а не тот, кто её ждал. Пустой ответ не запоминается: молчание
    источника - это не «ничего нет», и переспросить его следующему никто не мешает.
    """

    def __init__(self) -> None:
        self._found: dict[Hashable, _Answer] = {}
        self._running: dict[Hashable, threading.Thread] = {}
        self._lock = threading.Lock()

    def ask(self, key: Hashable, work: Callable[[], _Answer], timeout: float) -> _Answer | None:
        """Ответ по ключу в отведённый срок; не успел - ``None``, а нитка остаётся одна."""
        known = self.found(key)
        if known is not None:
            return known
        self.looker(key, work).join(timeout)
        return self.found(key)

    def found(self, key: Hashable) -> _Answer | None:
        """Ответ по ключу, если он уже приехал, - хоть бы и после чьего-то срока."""
        with self._lock:
            return self._found.get(key)

    def looker(self, key: Hashable, work: Callable[[], _Answer]) -> threading.Thread:
        """Нитка, отвечающая на ключ: уже поднятая, если она жива, иначе новая.

        Ждут её по своему сроку сами спрашивающие: у одного он длиннее, у другого короче,
        а нитка на всех одна. Ошибку она глотает сама - справка не вправе ронять того, кто
        её спросил.
        """

        def look() -> None:
            with contextlib.suppress(Exception):
                answer = work()
                if answer:
                    with self._lock:
                        self._found[key] = answer
            with self._lock:
                self._running.pop(key, None)

        with self._lock:
            running = self._running.get(key)
            if running is not None and running.is_alive():
                return running
            worker = threading.Thread(target=look, daemon=True, name=f"looker-{key}")
            self._running[key] = worker
        worker.start()
        return worker
