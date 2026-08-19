"""Фоновый добор справки к меню франшизы; зовёт его печать меню."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterable

from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.settings import FACTS_BUDGET, TOPUP_LIMIT
from torrcast.ports.blurb_source import BlurbSource
from torrcast.ports.blurb_store import BlurbStore


class Facts:
    """Фоновый добор справки: :meth:`start` — и живи дальше, :meth:`get` — забери.

    Поток один на всю франшизу, а не по потоку на картину: оба источника отвечают
    пакетом, и четыре картины стоят ровно столько же, сколько одна.
    """

    def __init__(
        self,
        pictures: Iterable[tuple[str, int | None]],
        budget: float = FACTS_BUDGET,
        *,
        store: BlurbStore,
        source: BlurbSource,
    ) -> None:
        self.wanted = list(pictures)
        self.budget = budget
        self.store = store
        self.source = source
        self.found: dict[tuple[str, int | None], Fact] = {}
        self._done = threading.Event()
        self._thread: threading.Thread | None = None
        self._deadline = 0.0
        self._started = 0.0

    def start(self) -> None:
        """Пустить добор фоном. Ошибки внутри гасятся: справка не вправе ронять показ."""
        self._started = time.monotonic()
        self._deadline = time.monotonic() + self.budget
        if not self.wanted:
            self._done.set()
            return
        self.found = self.store.blurbs(self.wanted)
        if len(self.found) == len(self.wanted):  # всё уже лежит в кэше - сети не надо
            self._done.set()
            return
        self._thread = threading.Thread(target=self._work, daemon=True)
        self._thread.start()

    def get(self, title: str, year: int | None) -> Fact:
        """Справка по картине; не приехала к :attr:`budget` — пустая, и меню печатается.

        Дедлайн один на всё меню, а не бюджет на строку: иначе франшиза из четырёх картин
        ждала бы молчащий источник вчетверо дольше обещанного.
        """
        self._done.wait(max(0.0, self._deadline - time.monotonic()))
        return self.found.get((title, year), Fact())

    def finish(self) -> None:
        """Дать добору дописать кэш - уже ПОСЛЕ меню, чтобы следующее было полным.

        Дедлайн отпускает МЕНЮ, а не поток: тот идёт дальше и кладёт найденное на диск.
        В живом показе это и так успевает - пока человек читает меню и отвечает, поток
        давно закончил, и здесь ждать нечего. А вот там, где ход обрывается сразу за меню
        (``--dry``, отказ «картин много, а терминала нет»), процесс уносил поток с собой:
        в кэш не попадало ничего, и следующий заход снова печатал голое меню.

        Ждём не с нуля, а остаток :data:`TOPUP_LIMIT` от старта: полторы секунды бюджета
        уже прошли, и на Ctrl-C это оставляет не задержку, а её хвостик.
        """
        thread = self._thread
        if thread is not None:
            thread.join(max(0.0, self._started + TOPUP_LIMIT - time.monotonic()))

    def _work(self) -> None:
        try:
            # Спрашиваем только ненайденное: лежащее в кэше уже полное, и переспрашивать
            # его - значит занимать его именами место в пакете и рисковать записать
            # поверх полной справки её обеднённый повтор.
            missing = [key for key in self.wanted if key not in self.found]
            fresh, answered = self.source.fetch(missing, ready=self._ready)
            # Дописываем к тому, что уже лежало в кэше, а не заменяем: сеть отвечает только
            # про ненайденное, и присваиванием мы выбрасывали справку, которая у нас была.
            self.found = {**self.found, **fresh}
            # Пустой ответ тоже запоминаем - иначе поход за ним повторяется каждое меню.
            # Но только про то, о чём источник РЕАЛЬНО ответил: неполный ответ не говорит
            # про промолчавшую часть ничего, и «статьи нет» про неё - выдумка на весь срок
            # кэша (🔴 TC-568).
            self.store.remember(
                fresh, [key for key in missing if key not in fresh and key in answered]
            )
        except Exception:
            pass
        finally:
            self._done.set()

    def _ready(self, part: dict[tuple[str, int | None], Fact]) -> None:
        """Описания - в меню, не дожидаясь украшений.

        🔴 TC-561. Меню и так ждёт свои полторы секунды - вопрос лишь в том, получает ли
        оно за них хоть что-нибудь. Описание приезжает первым шагом, рейтинг и хронометраж
        - вторым, вдвое более медленным; складывать их было незачем: пока ждали второй,
        пропадал и первый. Теперь дошедшее до дедлайна печатается, а опоздавшее дописывает
        кэш (:meth:`finish`) и достаётся следующему показу целиком.

        В кэш отсюда не пишем: на диск ложится итог, а не полуфабрикат - иначе описание
        без рейтинга закрыло бы дорогу полной справке на неделю вперёд. И уже добытое
        полуфабрикатом не накрываем: лежащее слева уступает тому, что уже есть.
        """
        self.found = {**part, **self.found}
