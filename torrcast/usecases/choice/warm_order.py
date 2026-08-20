"""Порядок прогрева под меню: первой греется та картина, в которую попадёт Enter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.choice.first_alive import first_alive

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def warm_order(plans: list[Plan]) -> list[Plan]:
    """Кого греть под меню: сначала дефолт, дальше по хронологии списка.

    Греется голова этого списка (:data:`~torrcast.domain.prewarm_settings.PREWARM` картин), и
    первой в ней обязана стоять та картина, в которую попадёт Enter (:func:`first_alive`).
    Иначе прогрев достаётся соседям: дефолт стоит пятым у «ведьмак s2e4», шестым у
    «медведь s2e7», седьмым у «евангелион s1e1» и девятым у «блич s1e1», то есть за
    головой списка, и человек, нажавший Enter, ждал бы подъёма роя с нуля.

    Остальные картины греются в порядке списка не от лени: список на экране
    хронологический, и человек, который с дефолтом не соглашается, тычет в соседний номер.
    """
    default = first_alive(plans)
    return [plans[default - 1], *(p for n, p in enumerate(plans, start=1) if n != default)]
