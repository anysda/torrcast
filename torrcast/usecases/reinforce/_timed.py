"""Пересборка плана на настоящей длительности картины, как только её назвала справка."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.minutes_of import minutes_of
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.ports.journal import journal
from torrcast.usecases.reinforce._plan_for import _plan_for

if TYPE_CHECKING:
    from torrcast.domain.config import Config
    from torrcast.ports.choice_types import Args, _Plan


class _Told(Protocol):
    """Справка о картинах в объёме, который нужен пересборке: один вопрос про одну.

    Полная :class:`torrcast.usecases.facts.Facts` сюда не приходит: фоновый добор, его
    бюджет и его поток - дело меню, а плану нужен готовый ответ про одну картину.
    """

    def get(self, title: str, year: int | None) -> Fact: ...


def _timed(
    plan: _Plan, facts: _Told | None, args: Args, config: Config, profile: Profile = CAUTIOUS
) -> _Plan:
    """Пересобрать план на НАСТОЯЩЕЙ длительности картины, как только её назвала справка.

    🔴 TC-185. Битрейт релиза отбор считает делением размера раздачи на длительность
    (:func:`bitrate_of`), а длительности до ffprobe он не знает и берёт прикидку «фильм
    это два часа». Прикидка не нейтральна: у «Интерстеллара» (2 ч 49 мин) она завышает
    битрейт в 1.41 раза, у «Форреста Гампа» (2 ч 22 мин) — в 1.18, и честный 1080p,
    лежащий под потолком, отсекался потолком, которого он не переходил. Молча: отказ
    арифметики строки не печатает.

    Потолки при этом не двигаются ни на знак — чинится ЗНАМЕНАТЕЛЬ.

    Лишнего запроса тут нет ни одного: хронометраж уже приехал в справке к меню
    («2 ч 49 мин» печатается рядом с рейтингом), и спрашивается он у той же
    :class:`~torrcast.facts.Facts`, которую меню уже дождалось. Поэтому и зовётся это
    ПОСЛЕ меню: до меню справки ещё нет, а ждать её на пути старта нельзя.

    Справка молчит (нет статьи, нет сети, картины нет в выгрузке) — план остаётся на
    прикидке, и это решение не молчаливое: событие ``runtime`` уходит в недельный след
    (:func:`torrcast.trace.emit`) с тем же числом, которым считался битрейт.
    """
    fact = facts.get(plan.picture.title, plan.picture.year) if facts is not None else Fact()
    minutes = minutes_of(fact.runtime)
    if minutes <= 0:
        journal().emit(
            "select", "runtime", secs=round(plan.runtime), src="guess", title=plan.picture.title
        )
        return plan
    fresh = _plan_for(plan.picture, args, config, profile, runtime=minutes * 60.0)
    fresh.kin = plan.kin
    journal().emit(
        "select",
        "runtime",
        secs=round(fresh.runtime),
        src="facts",
        title=plan.picture.title,
        was=round(plan.runtime),
    )
    return fresh
