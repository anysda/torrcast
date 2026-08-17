"""Круг по индексерам: каждому свой запрос в свой бюджет, все разом."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Final

from torrcast.adapters.prowlarr.ask_indexer import ask_indexer
from torrcast.adapters.prowlarr.merge import merge
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi
from torrcast.adapters.prowlarr.raw_result import RawResult
from torrcast.adapters.prowlarr.search_url import search_url
from torrcast.domain.circle_indexers import Indexer
from torrcast.domain.indexer_budget import indexer_budget
from torrcast.domain.infra_error import InfraError
from torrcast.domain.response_budget import response_budget
from torrcast.domain.wait_indexer import wait_indexer

#: Запас поверх личного бюджета на ожидание потока: сам запрос уже ограничен бюджетом,
#: и эта секунда нужна лишь на то, чтобы поток успел записать ответ и поднять флаг.
#: Без неё круг изредка объявлял молчуном того, кто ответил на последней миллисекунде.
ASK_SLACK: Final = 1.0


@dataclass(slots=True)
class _Ask:
    """Один спрошенный индексер: место под ответ и флаг «поток закончил».

    Поток свой и демонский, а не из пула: опоздавший живёт дольше круга (TC-118), и
    пул задержал бы на нём выход процесса - потоки пула дожидаются на atexit, демонские
    умирают вместе с командой.
    """

    name: str
    budget: float
    done: threading.Event = field(default_factory=threading.Event)
    rows: list[RawResult] | None = None
    ms: int = 0
    err: InfraError | None = None


class IndexerCircle:
    """Кого спросили за этот поиск, кто ответил, кто смолчал и кто ещё в пути."""

    def __init__(
        self,
        api: ProwlarrApi,
        *,
        slack: float = ASK_SLACK,
        budget_of: Callable[[str], float] = indexer_budget,
    ) -> None:
        self.api = api
        self.slack = slack
        self.budget_of = budget_of
        #: Сколько строк отдал каждый ответивший - по именам.
        self.counts: dict[str, int] = {}
        #: Сколько миллисекунд каждый ответивший держал круг.
        self.spent: dict[str, int] = {}
        #: Кто не уложился в свой бюджет, в порядке круга.
        self.lost: list[str] = []
        #: 🔴 TC-510. Кто ответил нам за ЭТОТ поиск - хоть строкой, хоть честным нулём.
        #: Копится по всем кругам поиска, а не по последнему: клиент живёт ровно один
        #: поиск, и вопрос «было ли чем искать» - вопрос о поиске целиком.
        self.answered: set[str] = set()
        #: Опоздавшие: круг ушёл по опорным, а эти ещё в пути (TC-118).
        self._late: list[_Ask] = []

    def begin(self) -> None:
        """Начать новый расклад: кругов у поиска бывает два, а счёт по ним общий.

        Ответившие (:attr:`answered`) переживают это нарочно: они про весь поиск, а не
        про последний его круг.
        """
        self.counts = {}
        self.spent = {}
        self.lost = []

    def waiting(self) -> tuple[str, ...]:
        """Имена тех, кто ещё в пути: круг их не дождался, а долив может."""
        return tuple(ask.name for ask in self._late)

    def run(
        self, pairs: Sequence[Indexer], query: str, limit: int, cap: float = 0.0
    ) -> tuple[list[list[RawResult]], InfraError | None]:
        """Один круг: каждому свой запрос в свой бюджет, все разом.

        ``cap`` - потолок бюджета для этого круга: ноль на первом (он и есть поиск), а на
        каждом следующем - остаток цели (TC-228).

        🔴 Круг кончается, когда ответили опорные
        (:func:`~torrcast.domain.wait_indexer.wait_indexer`), а не последний из спрошенных.
        Кто к этой секунде не успел - не потерян и не молчун: его поток живёт дальше, а
        выдачу забирает :meth:`late` уже после показа списка (TC-118). Раньше меню ждало
        ВСЕХ, и молчун жёг полный личный бюджет: на холодном старте тяжёлой картины
        (замер TC-108) это 47.8% всего времени пути, а по второму источнику (`cast log`)
        Nyaa.si замолчал после 3-4 запросов и стоил ровно 20.1 с - при том, что в здоровых
        кругах отдавал по этим же запросам НОЛЬ строк. Опорных в круге нет вовсе (фолбэк по
        анимешным, TC-229) - тогда ждём всех: иначе ждать было бы некого и круг
        возвращался бы пустым.

        Возвращает выдачи и причину последней потери - она понадобится, если смолчат все.
        """
        asked = [self._spawn(query, limit, num, name, cap) for num, name in pairs]
        core = [ask for ask in asked if wait_indexer(ask.name)] or asked
        for ask in core:
            ask.done.wait(ask.budget + self.slack)
        got: list[list[RawResult]] = []
        why_lost: InfraError | None = None
        for ask in asked:
            if not ask.done.is_set():  # опоздал, но не потерян: доедет доливом
                self._late.append(ask)
                # Опорного уже прождали весь бюджет круга. На пути к показу это честное
                # «молчит», даже если фоновый запрос позднее привезёт строки. Остальных
                # круг не держал вовсе, поэтому раньше личного срока молчунами не зовём.
                if ask in core:
                    self.lost.append(ask.name)
                continue
            self.spent[ask.name] = ask.ms
            if ask.rows is None:
                self.lost.append(ask.name)
                why_lost = ask.err
            else:
                # Честный ноль - тоже ответ (TC-510): каталог свой источник показал, и
                # пустота такого поиска - это «нет такого фильма», а не «нечем искать».
                self.answered.add(ask.name)
                got.append(ask.rows)
                self.counts[ask.name] = len(ask.rows)
        return got, why_lost

    def late(self, wait: float = 0.0) -> list[RawResult]:
        """Выдача опоздавших: круг ушёл по опорным, а эти доехали уже потом (TC-118).

        🔴 Зовётся ОДИН раз и только там, где долив уже ничего не подменяет: список
        картин человек к этой секунде прочитал и ответил на него, и менять под курсором
        нечего. Что доехало - забирается, кто ещё в пути - остаётся ждать следующего
        вызова; ``wait`` больше нуля нужен ровно одному случаю: показывать нечего вовсе,
        и тогда опоздавший - единственное, что вообще может приехать.

        Не ждать по умолчанию - тоже решение: долив нужен там, где он бесплатен. Секунда
        ожидания здесь стоила бы ровно столько же, сколько стоила бы в круге, - а круг от
        неё и уходил. ``wait`` - срок на ВЕСЬ долив, а не на каждого опоздавшего: двое в
        пути стоили бы двойного ожидания, а звавший отмерял его один раз.
        """
        rows: list[RawResult] = []
        rest: list[_Ask] = []
        deadline = time.monotonic() + wait
        for ask in self._late:
            if wait > 0:
                ask.done.wait(max(0.0, deadline - time.monotonic()))
            if not ask.done.is_set():
                rest.append(ask)
                continue
            if ask.rows is not None:
                # Опоздавший тоже ОТВЕТИЛ (TC-510): пусть после круга, но каталог свой
                # он показал, и молчанием всего поиска это уже не назовёшь.
                self.answered.add(ask.name)
                rows += ask.rows
        self._late = rest
        return merge(rows) if rows else []

    def _spawn(self, query: str, limit: int, num: int, name: str, cap: float = 0.0) -> _Ask:
        """Пустить один индексер отдельным потоком и вернуть место под его ответ."""
        budget = self.budget_of(name)
        ask = _Ask(name=name, budget=min(budget, cap) if cap else budget)
        url = search_url(self.api.base_url, self.api.apikey, query, limit, num)

        def work() -> None:
            # Бюджет ``ask`` отвечает только за критический путь. Сам запрос живёт в
            # личный срок индексера, чтобы потолок второго круга не обрывал быстрый
            # ответ на границе, а поздний ответ опорного мог доехать в долив.
            ask.rows, ask.ms, ask.err = ask_indexer(self.api.get_json, url, response_budget(name))
            ask.done.set()

        threading.Thread(target=work, daemon=True, name=f"idx-{name}").start()
        return ask


__all__ = ["ASK_SLACK", "IndexerCircle"]
