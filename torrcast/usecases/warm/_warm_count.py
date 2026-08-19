"""Счёт прогретого: сколько секунд показ и правда возьмёт с диска и что ещё не готово.

Спрашивает их состояние прогрева (:class:`torrcast.usecases.warm.warmer_state._State`).
"""

from __future__ import annotations

from torrcast.ports.recode.encoding_key import EncodingKey
from torrcast.usecases.warm._state import Grid
from torrcast.usecases.warm.vault import Vault


def _warmed(grid: Grid, vault: Vault, cap: int) -> float:
    """Сколько секунд фильма показ может взять с диска.

    Считается не «сколько лежит», а «что возьмут»: копия тяжелее потолка приёмника
    наружу не идёт (:meth:`torrcast.usecases.feed_pack.feed.Feed._warm`), под таким местом
    работает живая упаковка - значит, обрыва связи оно не переживёт и запасом не является.
    Тяжёлое место входит в счёт, когда прогрев приведёт его к перекоду (:func:`_spots_left`), то
    есть к тому же виду, в котором его отдаёт показ.

    Замер, ради которого счёт такой («Тачки» 2006, 1080p): тяжелее потолка 38 % кусков,
    и число называло запас, которого у человека нет.
    """
    return sum(grid.span(slot) for slot in vault.slots(cap))


def _all_warmed(
    grid: Grid, vault: Vault, cap: int, spots: tuple[int, ...], encode: EncodingKey | None
) -> bool:
    """Весь фильм на диске: показ дальше не нуждается в сети вовсе.

    Считается ровно то же, что и в :func:`_warmed`, - только то, что показ и правда
    возьмёт с диска: копия тяжелее потолка приёмника наружу не идёт
    (:meth:`torrcast.usecases.feed_pack.feed.Feed._warm`), и пока на месте тяжёлого куска лежит
    она, а не перекод (:func:`_spots_left`), «готово» - ложь: человек выключит интернет и
    упрётся в темноту на первом же тяжёлом месте.
    """
    return len(vault.slots(cap)) >= grid.count and not _spots_left(vault, spots, encode)


def _spots_left(
    vault: Vault, spots: tuple[int, ...], encode: EncodingKey | None
) -> tuple[int, ...]:
    """Тяжёлые куски, которые ещё не перекодированы точечно.

    Кусок берётся в работу, только когда копия уже лежит: перекод идёт поверх неё, и
    порядок «сначала весь фильм копией, потом тяжёлые места» держит одно свойство -
    прогретое в любой момент играбельно целиком, даже если прогрев сняли посередине.
    """
    if not spots or encode is None:
        return ()
    return tuple(slot for slot in spots if vault.have(slot) and not vault.spot(slot).exists())
