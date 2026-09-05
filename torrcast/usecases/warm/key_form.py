"""Отпечаток ФОРМЫ ключа прогретого: чем ключи этой сборки отличаются от прежних.

Пишет его в паспорт каталог прогретого (:class:`torrcast.usecases.warm.vault.Vault`), а
читает по нему сборщик места (:func:`torrcast.usecases.warm.strip_forms.strip_forms`).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Final

from torrcast.domain.segment_container import FMP4, MPEGTS, SegmentContainer
from torrcast.usecases.warm.warm_key import warm_key


class _Rod:
    """Мерная сетка отпечатка: числа взяты произвольно и не меняются никогда.

    Отпечаток обязан меняться от правки СПОСОБА счёта ключа, а не от того, что мерили,
    поэтому вход у него один и тот же навсегда. Сетка тут своя, а не настоящая: отпечаток
    считается на импорте, когда никакого показа ещё нет и спрашивать сетку не у кого.
    """

    count = 3
    duration = 30.0
    origin = 0.0
    on_keys = True
    weigh: Callable[[float, float], float] | None = None

    def start(self, slot: int) -> float:
        return 10.0 * slot

    def end(self, slot: int) -> float:
        return 10.0 * slot + 10.0

    def span(self, slot: int) -> float:
        return self.end(slot) - self.start(slot)

    def slot_at(self, seconds: float) -> int:
        return int(seconds // 10.0)

    def manifest(self, container: SegmentContainer = MPEGTS) -> str:
        return str(container)


class _Decision:
    """Мерное решение о кодировании: без него отпечаток слеп к тем звеньям ключа,
    которых на копийном показе нет вовсе."""

    preset = "veryfast"
    mbit = 28.0
    mark = "mark"
    imprint = "imprint"


def _stamp() -> str:
    """Отпечаток формы: два ключа мерного показа, с пустыми звеньями и с полными.

    Двумя, а не одним: половина звеньев ключа появляется только на перекоде (решение,
    точечные места, озвучка), и ключ одного копийного показа правку их СБОРКИ не заметил
    бы. Считается тем же :func:`warm_key`, которым живёт продукт, - собственная копия его
    устройства разъезжалась бы с ним молча, и ровно в тот день, когда форма и меняется.
    """
    bare = warm_key("rod", 0, _Rod())
    full = warm_key("rod", 0, _Rod(), _Decision(), (1, 2), FMP4, "voice", _Decision())
    return hashlib.sha1(f"{bare}|{full}".encode()).hexdigest()[:16]


#: Отпечаток формы ключа ЭТОЙ сборки. Полка, у которой в паспорте стоит другой отпечаток
#: (или не стоит никакого - её клали до того, как отпечаток начали записывать), не
#: находится больше ни по одному ключу этой сборки: её содержимое уже никому не отдадут.
KEY_FORM: Final = _stamp()
