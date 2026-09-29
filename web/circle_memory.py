"""Память кругов раздач: найденное на срок, отказ круга на минуту, диск на сутки.

Круг, где ответил не каждый спрошенный индексер, на диске лежит с меткой и сменяется
следующим, не беднее его. Минуту он ответ и тому, кто спрашивает сам; после неё поиск
спрашивает сеть, а экран держит его свой срок, как любой круг.

Пустой ответ помнится коротко, по образцу Torrentio (``addon/lib/cache.js``, Apache-2.0,
github.com/TheBeastLT/torrentio-scraper): без памяти отказа каждый переспрос карточки
картины без раздач заново гнал круг по индексерам, раз в секунду, пока открыта страница.

Отказ тут любой, каким круг кончился: и «ничего не нашлось», и сорванный инфраструктурой.
Помнилось только первое, а второе не оставляло ни находки, ни отказа - и тогда круг для
всех, кто его ждёт, навсегда оставался «ещё считается».
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.slugify import slugify
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.usecases.discover.cut_circle import CutCircle
from torrcast.usecases.discover.told_circle import ToldCircle
from web.circle_disk import CircleDisk
from web.torn_circle import TornCircle

if TYPE_CHECKING:
    from torrcast.usecases.discover.told_indexer import Told
    from torrcast.usecases.select.plan import Plan

#: Сколько помнится подтверждённое «ничего не нашлось».
EMPTY_TTL: Final = 60.0


@dataclass
class CircleMemory:
    """Согретые круги и свежие отказы; часы подставные ради тестов."""

    clock: Callable[[], float]
    ttl: float
    #: Диск кругов и сборка круга по записи; без них память живёт только в процессе.
    disk: CircleDisk | None = None
    replay: Callable[[str, list[Told]], list[Plan]] | None = None
    _found: dict[str, tuple[list[Plan], float]] = field(default_factory=dict, repr=False)
    #: Чем круг кончился, если не раздачами: отказ поиска или сорвавшая его инфраструктура.
    _empty: dict[str, tuple[TorrcastError, float]] = field(default_factory=dict, repr=False)
    #: Last circle that came from the network, poorer or not, and keys shown from disk only.
    _landed: dict[str, tuple[list[Plan], float]] = field(default_factory=dict, repr=False)
    _revived: set[str] = field(default_factory=set, repr=False)
    #: When a circle not every indexer answered stops answering one who asks (:meth:`plans`).
    _asker: dict[str, float] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @staticmethod
    def key(query: str) -> str:
        """Один ключ круга на всех: поиск, прогрев, карточка и «похожие»."""
        return query.strip()

    def plans(self, query: str, retry: bool = False) -> list[Plan] | None:
        """Согретый круг, пустой список для свежего отказа, иначе ``None``.

        Сорванный круг пуст так же (ждущие его не переспрашивают сеть до срока), но это
        :class:`TornCircle`: читающий вердикт отличит «не знаю» от «нет раздач».
        ``retry`` - спрашивает человек: неполный круг старше минуты ему не ответ.
        """
        key, now = self.key(query), self.clock()
        with self._lock:
            found = None if retry and self._asker.get(key, now + 1) <= now else self._found.get(key)
            if found is not None and found[1] > now:
                return found[0]
            empty = self._empty.get(key)
        if empty is None or empty[1] <= now:
            return None
        return [] if isinstance(empty[0], NotFoundError) else TornCircle(empty[0])

    def live(self, query: str) -> list[Plan] | None:
        """Круг, пришедший из сети в свой срок, а не поднятый с диска.

        Показ с карточки играет и круг с диска; сетевой нужен, когда отбор по дисковому
        кончился ничем (:func:`web.show_stage._card_renewed`), и выдаче HA.
        """
        with self._lock:
            landed = self._landed.get(self.key(query))
        return landed[0] if landed is not None and landed[1] > self.clock() else None

    def alike(self, query: str) -> list[Plan] | None:
        """Сетевой круг этой строки, а нет его - строки, что отличается регистром и знаками.

        История несёт строку слагом («рататуй»), а круг согрет строкой набора («Рататуй»).
        Своя ли в нём картина, решает спросивший (:func:`web.own_plan.own_plan`).
        """
        if (own := self.live(query)) is not None:
            return own
        slug, now = slugify(query), self.clock()
        with self._lock:
            for key, (plans, until) in self._landed.items():
                if until > now and slug and slugify(key) == slug:
                    return plans
        return None

    def revived(self, query: str) -> bool:
        """Показывается ли круг, поднятый с диска, за которым из сети ещё ничего не пришло."""
        with self._lock:
            return self.key(query) in self._revived

    def refusal(self, query: str, retry: bool = False) -> TorrcastError | None:
        """Свежий отказ этого запроса, если он есть.

        ``retry`` - клик по живой «Играть»: пустота, за которую не ответил весь каталог
        (``whole``), не повод отказать клику, и он ищет заново. Только «ничего», сказанное
        каждым индексером, стоит свою минуту и против клика.
        """
        key = self.key(query)
        with self._lock:
            empty = self._empty.get(key)
            if retry and empty is not None and not _whole(empty[0]):
                del self._empty[key]
                return None
        return empty[0] if empty is not None and empty[1] > self.clock() else None

    def keep(self, query: str, plans: list[Plan]) -> None:
        """Запомнить непустую находку; пустая - не находка, урезанная - на минуту.

        Неполный круг (:meth:`poorer`) живой полный не вытесняет, а без него живёт минуту.
        Круг, где ответил не каждый спрошенный индексер (:func:`_part`), спрашивающему сам
        ответ минуту (:meth:`plans`): фон и экран держат его свой срок и сети не зовут.
        """
        if not plans:
            return
        key, poorer, part = self.key(query), self.poorer(query, plans), _part(plans)
        ttl = EMPTY_TTL if poorer or isinstance(plans, CutCircle) else self.ttl
        with self._lock:
            self._landed[key] = (plans, self.clock() + (EMPTY_TTL if part else ttl))
            self._revived.discard(key)
            shown = self._found.get(key)
            if poorer and shown is not None and shown[1] > self.clock():
                return
            self._found[key] = (plans, self.clock() + ttl)
            self._asker[key] = self.clock() + EMPTY_TTL if part else float("inf")
            self._empty.pop(key, None)

    def poorer(self, query: str, plans: list[Plan]) -> bool:
        """Промолчал ли в круге источник, чьи раздачи есть в записанном на диске.

        Метка урезанного (:class:`CutCircle`) ставится по отсечке переходника и пропускает
        ноль, пришедший раньше неё (JacRed: 0 за 3060 мс), а число строк честно гуляет.
        A whole circle always replaces a marked entry; a part one only when it lost no source.
        """
        told = plans.told if isinstance(plans, ToldCircle) else []
        kept = self.disk.told(self.key(query)) if self.disk is not None and told else None
        if not kept or self.disk is None or (self.disk.part(self.key(query)) and not _part(plans)):
            return False
        return bool(_sources(kept) - _sources(told))

    def revive(self, query: str) -> list[Plan] | None:
        """Круг с диска, собранный заново без сети; ``None`` - записи нет или она стара."""
        if self.disk is None or self.replay is None:
            return None
        told = self.disk.told(self.key(query))
        try:
            plans = None if not told else self.replay(query, told)
        except TorrcastError:
            return None
        if not plans:
            return None
        plans = list(plans)  # a plain list: what came from disk is not written back
        with self._lock:
            self._found[self.key(query)] = (plans, self.clock() + self.ttl)
            self._revived.add(self.key(query))
        return plans

    def store(self, query: str, plans: list[Plan]) -> None:
        """Записать круг на диск, если он не беднее лежащего; пустой туда не идёт.

        Неполный ложится с меткой; сменив не беднее себя полный, он стоит за полный.
        """
        told = plans.told if isinstance(plans, ToldCircle) else []
        if self.disk is None or not plans or not told or self.poorer(query, plans):
            return
        key = self.key(query)
        full = self.disk.told(key) is not None and not self.disk.part(key)
        self.disk.keep(key, told, part=_part(plans) and not full)

    def refuse(self, query: str, error: TorrcastError) -> None:
        """Запомнить, чем кончился круг, на :data:`EMPTY_TTL`.

        Не только «ничего не нашлось»: сорванный круг тоже кончился, и ждущим его надо
        сказать об этом словами, а не держать их на «ещё считается» без конца.
        """
        with self._lock:
            self._empty[self.key(query)] = (error, self.clock() + EMPTY_TTL)


def _part(plans: list[Plan]) -> bool:
    """A circle some asked indexer did not answer: cut short, silent, or refusing.

    One Prowlarr took out of reach was not asked, and it does not make the circle part.
    """
    return isinstance(plans, CutCircle) or (isinstance(plans, ToldCircle) and not plans.heard)


def _whole(error: TorrcastError) -> bool:
    return isinstance(error, NotFoundError) and error.whole


def _sources(told: list[Told]) -> set[str]:
    return {
        name for said in told for row in said[4] for name in (*row.indexers, row.indexer) if name
    }


__all__ = ["EMPTY_TTL", "CircleMemory"]
