"""Отладочная ручка ``cast releases <запрос>``: таблица релизов каждой картины и выход.
Зовёт её :func:`torrcast.cli.releases.releases`, показ отсюда не начинается.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeAlias

from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.profile import Profile
from torrcast.domain.release import Release
from torrcast.domain.tune import tune as tune_profile
from torrcast.ports.progress import Progress
from torrcast.ports.progress import progress as progress_bar
from torrcast.usecases.choice import _named
from torrcast.usecases.discover import _search
from torrcast.usecases.rank import render_table
from torrcast.usecases.reinforce import _timed

if TYPE_CHECKING:
    from torrcast.ports.choice_types import Args, _Plan
    from torrcast.usecases.facts import Facts

    #: Чем ищется выдача: тот же поиск, что и у показа (:func:`_search`), либо ответ
    #: подделки в тесте. Тип назван подписью самого поиска, а не свободным `Any`:
    #: таблица зовёт его ровно этими четырьмя доводами и ждёт ровно планы картин.
    Search: TypeAlias = Callable[[Config, Args, Progress, Profile], list[_Plan]]

#: Внешний мир таблицы: настройки, справка о картинах, паспорт приёмника и память
#: показанного порядка. Кладёт их композиционный корень (:mod:`torrcast.runtime.wire`) -
#: файл, сеть и опрос устройства сценарию не назвать. Имена длиннее очевидных нарочно:
#: плоский namespace прежнего монолита (:mod:`torrcast.cli`) вписывает globals каждой
#: своей части в каждую другую, и короткий тёзка молча затирает функцию соседа.
_releases_settings: Callable[[], Config]
_releases_facts: Callable[[list[tuple[str, int | None]]], Facts]
_releases_detect: Callable[[Config], Choice]
_releases_remember: Callable[[str, dict[str, list[Release]]], None]


def _configure_releases_command(
    settings: Callable[[], Config],
    facts: Callable[[list[tuple[str, int | None]]], Facts],
    detect: Callable[[Config], Choice],
    remember: Callable[[str, dict[str, list[Release]]], None],
) -> None:
    """Назначить таблице релизов её внешний мир."""
    global _releases_settings, _releases_facts, _releases_detect, _releases_remember
    _releases_settings = settings
    _releases_facts = facts
    _releases_detect = detect
    _releases_remember = remember


def _cmd_releases(
    args: Args,
    search: Search | None = None,
    settings: Callable[[], Config] | None = None,
    facts_source: Callable[[list[tuple[str, int | None]]], Facts] | None = None,
    profile_choice: Callable[[Config], Choice] | None = None,
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
    settings = settings or _releases_settings
    facts_source = facts_source or _releases_facts
    profile_choice = profile_choice or _releases_detect
    config = settings()
    # Внутренний запрос той же формы, что пришёл: команда снимает с него своё слово
    # («releases») и играет остатком. Класс берётся у самого аргумента - разбор
    # командной строки живёт слоем выше, и сценарию его не назвать.
    inner = type(args)(query=list(args.query[1:]))
    if not inner.query:
        raise NotFoundError("что искать? cast releases <запрос>")
    chosen = profile_choice(config)
    config = tune_profile(config, chosen.profile)
    with progress_bar() as progress:
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
        _releases_remember(inner.title_query, shown)
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
