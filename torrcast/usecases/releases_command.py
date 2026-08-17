"""Отладочная ручка ``cast releases <запрос>``: таблица релизов каждой картины и выход.
Зовёт её :func:`torrcast.commands.main`, показ отсюда не начинается.
"""

# ruff: noqa: F821, F822

from __future__ import annotations

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.release import Release
from torrcast.usecases.choice import _named
from torrcast.usecases.discover import _search
from torrcast.usecases.rank import render_table
from torrcast.usecases.reinforce import _timed

__all__ = [
    "EXIT_OK",
    "Args",
    "Facts",
    "NotFoundError",
    "Progress",
    "Release",
    "_cmd_releases",
    "detect_profile",
    "load_config",
    "tune_profile",
]

from collections.abc import Callable
from typing import Any

from torrcast.domain.exit_codes import EXIT_OK
from torrcast.ports.module import module

for _module_name, _names in {
    "torrcast.console": ("Progress",),
    "torrcast.facts": ("Facts",),
    "torrcast.state": ("load_config",),
}.items():
    _dependency = module(_module_name)
    globals().update({name: getattr(_dependency, name) for name in _names})
detect_profile = module("torrcast.profile").detect
tune_profile = module("torrcast.profile").tune


def _cmd_releases(
    args: Args,
    search: Callable[..., Any] | None = None,
    settings: Callable[[], Any] | None = None,
    facts_source: Callable[..., Any] | None = None,
    profile_choice: Callable[..., Any] | None = None,
) -> int:
    """``cast releases <запрос>`` — отладочная ручка: таблица и выход.

    На счастливом пути таблицы нет вовсе: релиз выбирается сам. Но посмотреть, из чего
    он выбирал, иногда надо — и тогда рядом лежит ``cast <запрос> --release N``.

    Таблица спрашивает настоящую длительность, чтобы битрейт (а значит, и порядок
    раздач, и номера ``N``) совпал с тем, что сыграет ``cast`` по этому номеру.

    🔴 TC-446. Номер релиза относится к КАРТИНЕ своей таблицы, а не к выдаче целиком:
    нумерация в каждой таблице своя. Картин несколько - одним номером релиза картину не
    назвать, и таблица обязана это говорить: картины нумеруются (тем же номером, что в
    меню ``cast <запрос>`` и у ``--pick``), а строка-подсказка зовёт оба флага.

    🔴 TC-241. Судит таблица по ОБНАРУЖЕННОМУ профилю приёмника - тому самому, на
    который поедет показ: по осторожному умолчанию пометка «перекодируем» врала,
    обещая перекод там, где приставка играет копией. Определение профиля - то же, что
    на пути показа (:func:`~torrcast.profile.detect`), и оно не молчаливое: строка про
    профиль печатается всегда, и приёмника может не быть вовсе - тогда строка честно
    говорит, по какому профилю судим.
    """
    #: Внешние соседи таблицы: поиск, конфиг, справка и паспорт приёмника. Подделке
    #: отбора хватает её собственных ответов, в бою это сеть, диск и опрос устройства.
    search = search or _search
    settings = settings or load_config
    facts_source = facts_source or Facts
    profile_choice = profile_choice or detect_profile
    config = settings()
    inner = Args(query=list(args.query[1:]))
    if not inner.query:
        raise NotFoundError("что искать? cast releases <запрос>")
    chosen = profile_choice(config)
    config = tune_profile(config, chosen.profile)
    with Progress() as progress:
        plans = search(config, inner, progress, chosen.profile)
    facts = facts_source([(p.picture.title, p.picture.year) for p in plans])
    facts.start()
    try:
        print(f"профиль приёмника: {chosen.profile.title} - {chosen.how}")
        shown: dict[str, list[Release]] = {}
        for number, plan in enumerate(plans, start=1):
            plan = _timed(plan, facts, inner, config, chosen.profile)
            shown[plan.picture.key] = plan.ranked
            print()
            head = f"{_named(plan.picture)} - раздач {len(plan.ranked)}"
            # Номер картины тот же, что у пункта меню в `cast <запрос>` и у --pick:
            # порядок таблиц - порядок меню (:func:`_search` в обеих командах).
            print(f"{number}. {head}" if len(plans) > 1 else head)
            print(
                render_table(
                    plan.ranked,
                    plan.runtime,
                    plan.warn_mbit,
                    recode_at=plan.recode_at,
                    hard_mbit=plan.hard_mbit,
                )
            )
        module("torrcast.release_pin").remember(inner.title_query, shown)
        print()
        if len(plans) > 1:
            print(
                "играть конкретный: cast <запрос> --pick M --release N [--file N] - "
                "M это номер картины выше, N номер релиза в её таблице"
            )
        else:
            print("играть конкретный: cast <запрос> --release N [--file N]")
        return EXIT_OK
    finally:
        facts.finish()
