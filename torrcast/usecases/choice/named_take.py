"""Номер картины, взятой при сработавшем страже имени; 0 - страж молчит."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.slugify import slugify
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.usecases.choice.alive_numbers import alive_numbers
from torrcast.usecases.choice.asked_kind import asked_kind
from torrcast.usecases.choice.liveliness import liveliness
from torrcast.usecases.choice.named_elsewhere import _slugs, named_elsewhere

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def named_take(plans: list[Plan], asked: str) -> int:
    """Номер (с единицы) взятой картины, когда страж имени сработал; 0 - он молчит.

    🔴 TC-812, решение владельца 26-08-2026: страж «имя названо целиком»
    (:func:`named_elsewhere`, TC-715) остаётся стражем, но на обычном пути вопроса
    больше нет - печатается строка (:func:`named_taken_line`) и берётся живейшая.

    Живейшая ищется СРЕДИ НАЗВАННЫХ, пока хоть одна из них жива: человек назвал имя
    целиком, и уходить на картину, которую он не называл, - та самая подмена, ради
    которой страж и стоит. «Чернобыль» 2019 и 2022 названы оба - берётся более живая
    2019 года. Живой названной нет («блич s1e1»: у «Блича» 2004 рой ниже порога) -
    берётся самая живая из картин названного типа, а строка честно говорит, что
    названная не играет и почему.

    Срабатывание спрашивается у самого стража, а не переписывается: правило «когда имя
    считается названным целиком» живёт в одной редакции.
    """
    if not named_elsewhere(plans, asked):
        return 0
    alive = alive_numbers(plans, _chosen(plans, asked))
    pool = alive or asked_kind(plans)
    return max(pool, key=lambda n: (liveliness(plans[n - 1]), -n))


def _chosen(plans: list[Plan], asked: str) -> list[int]:
    """Номера целиком названных картин, суженные названным типом - как в строке стража."""
    name, _index = split_franchise_index(asked)
    key = slugify(name)
    numbers = asked_kind(plans)
    named = [n for n, plan in enumerate(plans, start=1) if key in _slugs(plan.picture)]
    return [n for n in named if n in numbers] or named
