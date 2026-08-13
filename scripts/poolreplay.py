#!/usr/bin/env python3
"""Офлайн-прогон боевого отбора по СОХРАНЁННЫМ выдачам индексеров.

Инструмент разработчика: в устанавливаемый пакет не входит.

    python scripts/poolreplay.py pools.jsonl
    python scripts/poolreplay.py pools.jsonl --query титаник
    python scripts/poolreplay.py pools.jsonl --glue
    python scripts/poolreplay.py pools.jsonl --jsonl out.jsonl
    python scripts/poolreplay.py pools.jsonl --ask '{}' --ask '{} 2'  # пары к тем же пулам

Живых служб не нужно ни одной: ни Prowlarr, ни TorrServer, ни приёмника, ни сети.
Выдачи в репе не лежат - путь к ним задаётся аргументом.

С ``--jsonl`` рядом с разбором ложится ПАСПОРТ прогона (``<вывод>.passport.json``):
коммит и отпечаток кода, отпечаток корпуса, дата, версия щупа. Без него сохранённый
прогон нечем пересчитать: см. :mod:`runpass`.

Формат ``pools.jsonl``, одна строка на запрос::

    {"query": "титаник",
     "rows": {"Knaben": [[имя, инфохэш, размер, сиды, индексер], ...], "RuTor": [...]}}

Ключ ``rows`` - выдача КАЖДОГО индексера отдельно, ровно так, как её отдал Prowlarr:
склейку врозь-выдач делает :func:`~torrcast.search.merge`, и делает её тут тот же код,
что и на живом пути.

Прогоняется ровно боевой тракт отбора и ровно его функциями::

    merge → to_releases → cluster (внутри неё glue) → pick_franchise → menu_order
          → _plan_for → candidates → queue_drops

Ни одна ступень здесь не переписана - щуп только зовёт и печатает. Это и есть повод
его завести: пока обвязку к сохранённым пулам писали заново под каждый замер, у
каждого замера получался свой счёт групп, и два замера нельзя было сравнить между собой.

Отбор судит осторожный профиль приёмника (:data:`~torrcast.profile.CAUTIOUS`) поверх
умолчаний настроек - никакой машины конкретного стенда в числах нет, и один и тот же
пул даёт один и тот же ответ где угодно.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import runpass

from torrcast.cli import (
    OFF_SEASON,
    Args,
    _ceiling_hides_name,
    _lacks_season,
    _Plan,
    _plan_for,
    drop_reason,
    queue_drops,
    season_reread,
    unfit_pool,
    voiceless_pool,
    worth_asking_original,
)
from torrcast.parse import (
    THIN_POOL,
    Picture,
    Release,
    cluster,
    menu_order,
    pick_franchise,
    split_franchise_index,
)
from torrcast.profile import CAUTIOUS, Profile, tune
from torrcast.search import _INDEXER_PAGE, Prowlarr, RawResult, merge, to_releases
from torrcast.state import Config

#: Что склеили и во что: список исходных кучек и получившаяся из них картина.
Merge = tuple[list[Picture], Picture]

#: Ступени боевого поиска ЗА первым кругом (TC-416). Щуп не проходит НИ ОДНОЙ: каждой
#: нужен живой круг по индексерам, а паспортной ещё и справка. Молчать об этом нельзя -
#: там, где гейт сработал, пул показа ШИРЕ пула щупа, и «мерено на корпусе» про такой
#: запрос значит «мерено по первому кругу», а не «мерено по тому, что играло».
BEYOND: dict[str, str] = {
    "раскладка": "_relayout: выдача пуста - повод заподозрить забытую раскладку",
    "цифра в имени": "_titled_number: цифра оказалась частью названия, поиск шёл обрубком",
    "паспорт": "_second_language: второе имя картины, за которым идут в справку",
    "потолок": "_ceiling_reinforce: имени запроса в каталоге нет, а страница обрезана",
    "сезон": "_season_reinforce: сериал найден, а раздач нужного сезона нет",
    "голос": "_voice_reinforce: русскую дорожку обещают только неиграбельные раздачи",
}

#: Путь, которого в сохранённом пуле не видно ВОВСЕ - даже гейт не спросить.
UNSEEN: str = (
    "опоздавшая выдача (Prowlarr.late → _topup): в пуле не записано, кто опоздал, "
    "и долить очередь после меню щупу нечем"
)


class ReplayMismatchError(RuntimeError):
    """Счёт раздач не сошёлся: очередь плюс отсев не равны пулу картины."""


@contextmanager
def watching_glue() -> Iterator[list[Merge]]:
    """Подсмотреть склейку внутри :func:`~torrcast.parse.cluster`, не трогая разбор.

    Другого способа увидеть, СКОЛЬКО кучек свелось в одну картину, у щупа нет: наружу
    :func:`~torrcast.parse.glue` отдаёт уже готовые картины, а второе имя
    (``Picture.also``) называет ровно одну из слитых - «три в одной» от «двух в одной»
    по нему не отличить. Переписывать разбор ради счёта нельзя: мерить надо то, что
    работает, а не его копию.
    """
    from torrcast import parse

    merges: list[Merge] = []
    original = parse.glue

    def spy(pictures: list[Picture]) -> list[Picture]:
        out = original(pictures)
        source = {id(r): p for p in pictures for r in p.releases}
        kept = {id(p) for p in pictures}
        for picture in out:
            if id(picture) in kept:  # картина прошла склейку как была - это не склейка
                continue
            members: list[Picture] = []
            for release in picture.releases:
                came = source.get(id(release))
                if came is not None and came not in members:
                    members.append(came)
            merges.append((members, picture))
        return out

    parse.glue = spy
    try:
        yield merges
    finally:
        parse.glue = original


@dataclass(slots=True)
class Replay:
    """Что тракт отбора сказал по одному сохранённому пулу."""

    query: str
    #: Строк в сохранённой выдаче, до склейки врозь-выдач по инфохэшу.
    raw_rows: int
    #: Раздач после :func:`~torrcast.search.merge`.
    results: int
    #: Каким запросом пул СНЯТ, если спрашивали его другим (``--ask``). Без этого пары
    #: «тот же пул, другой вопрос» не свести обратно: в выводе стоит вопрос, а не пул.
    pool: str = ""
    #: Все картины выдачи после разбора и склейки - каталог, из которого выбирает меню.
    catalog: list[Picture] = field(default_factory=list)
    #: Картины франшизы в порядке меню - это и есть верх меню.
    menu: list[Picture] = field(default_factory=list)
    #: Планы тех картин меню, у которых пул отбора не пуст.
    plans: list[_Plan] = field(default_factory=list)
    merges: list[Merge] = field(default_factory=list)
    #: Пул тощий: строк за самой полной картиной меньше :data:`THIN_POOL`.
    thin: bool = False
    #: Пул негоден: играть нечего ни у одной картины меню (:func:`unfit_pool`).
    unfit: bool = False
    #: Ступени :data:`BEYOND`, чей гейт на ЭТОМ пуле сработал бы: показ ушёл бы за вторым
    #: кругом, а щуп остался с первым. Считано по первому пулу - боевой поиск спрашивает
    #: те же гейты ПОСЛЕ каждого добора, и после чужого круга ответ бывает другим.
    beyond: list[str] = field(default_factory=list)

    @property
    def pictures(self) -> int:
        """Картин в каталоге всего - вся выдача, не только спрошенная франшиза."""
        return len(self.catalog)

    @property
    def missed(self) -> list[Picture]:
        """Картины каталога, которых :func:`pick_franchise` в меню не пустил.

        Это приговор отдельной ступени, и молчать о нём нельзя: человек спросил имя, а
        часть найденного до списка не доехала - иногда законно (чужие тёзки), иногда нет.
        """
        shown = {p.key for p in self.menu}
        return [p for p in self.catalog if p.key not in shown]

    @property
    def top(self) -> Picture | None:
        """Первая строка меню: список уже расставлен :func:`menu_order`."""
        return self.menu[0] if self.menu else None

    @property
    def default(self) -> Picture | None:
        """Что играет по Enter: верхняя картина меню, для которой построен план."""
        return self.plans[0].picture if self.plans else None

    @property
    def above_default(self) -> list[Picture]:
        """Картины франшизы, стоящие ВЫШЕ дефолта и плана не имеющие (TC-340).

        Человек их не видит вовсе: список ему печатается по планам
        (:func:`~torrcast.cli.menu_lines`), а не по всем картинам франшизы, и первым
        пунктом у него стоит дефолт. Пока щуп звал «верхом меню» первую картину
        :func:`~torrcast.parse.menu_order`, колонка врала ровно про них - печатала
        название и приписывала «→ Enter: другая» там, где никакого выбора человеку
        не показывали.
        """
        planned = {plan.picture.key for plan in self.plans}
        above: list[Picture] = []
        for picture in self.menu:
            if picture.key in planned:
                break
            above.append(picture)
        return above

    @property
    def any_picture_playable(self) -> bool:
        """Есть ли хоть какая-нибудь картина, которую Enter сможет запустить."""
        return self.default is not None

    @property
    def default_is_menu_top(self) -> bool:
        """Совпал ли дефолт с ПЕРВОЙ СТРОКОЙ меню - и только это.

        🔴 Мерой подмены это не является, и звать её «сыграла спрошенная» нельзя: дефолт
        франшизы это первая ЖИВАЯ часть, и она законно бывает не первой строкой (TC-529).
        Спросили «титаник» - верх меню Титаник 1943 года, а поедет на ТВ Титаник 1997-го,
        потому что у первого рой мёртв; спросили «фарго s3e1» - верх меню фильм 1996 года,
        у которого такой серии нет вовсе. Ложь тут ровно одна: назвать это потерей.
        Отвечает на вопрос «сыграла ли спрошенная картина» только СРАВНЕНИЕ С ЭТАЛОНОМ,
        и живёт оно в счёте (:func:`runreport.availability`), а не в одиночном прогоне.
        """
        return (
            self.top is not None and self.default is not None and self.top.key == self.default.key
        )


def batches_of(record: dict[str, Any]) -> list[list[RawResult]]:
    """Сохранённые строки индексеров → пачки :class:`RawResult`, битые строки прочь."""
    out: list[list[RawResult]] = []
    rows = record.get("rows")
    if not isinstance(rows, dict):
        return out
    for lines in rows.values():
        batch: list[RawResult] = []
        for line in lines or ():
            try:
                batch.append(RawResult.build(*list(line)[:5]))
            except (ValueError, TypeError):
                continue
        if batch:
            out.append(batch)
    return out


def replay(
    query: str,
    batches: list[list[RawResult]],
    config: Config,
    profile: Profile,
    capped: tuple[str, ...] = (),
    pool: str = "",
) -> Replay:
    """Прогнать один пул по боевому тракту отбора.

    ``capped`` - индексеры, отдавшие полную страницу (:func:`capped_of`): единственное
    свойство живого клиента, которое гейт потолка спрашивает и которое сохранённый пул
    ещё помнит. ``pool`` - каким запросом пул снят, если ``query`` спрашивает иначе.
    """
    args = Args(query=query.split())
    raw = merge(*batches) if batches else []
    with watching_glue() as merges:
        pictures = cluster(to_releases(raw))
    found = menu_order(pick_franchise(args.title_query, pictures))
    # Номер при имени сериала - сезон, и читает его тут ТА ЖЕ функция, что и показ
    # (:func:`~torrcast.cli.season_reread`, TC-363): иначе планы строились бы по первому
    # сезону там, где спрошен второй, - и разошлись бы молча.
    name, index = split_franchise_index(args.title_query)
    if (reread := season_reread(args, name, index, found, pictures)) is not None:
        args, index = reread, None
    plans = [p for p in (_plan_for(pic, args, config, profile) for pic in found) if p.ranked]
    return Replay(
        query=query,
        raw_rows=sum(len(b) for b in batches),
        results=len(raw),
        pool=pool or query,
        catalog=pictures,
        menu=found,
        plans=plans,
        merges=merges,
        thin=max((p.rows for p in found), default=0) < THIN_POOL,
        unfit=bool(found) and unfit_pool(found, args, config, profile),
        beyond=beyond_first_circle(
            raw, pictures, found, args, name, index, config, profile, capped
        ),
    )


def capped_of(record: dict[str, Any]) -> tuple[str, ...]:
    """Кто из индексеров отдал полную страницу - по сохранённой выдаче.

    Это НЕ переписанная ступень, а восстановленное свойство клиента: боевой круг считает
    его ровно так же и той же меркой (:data:`~torrcast.search._INDEXER_PAGE`), просто
    считает по своим строкам, а тут они лежат на диске, разложенные по индексерам.
    Опоздавших в счёте нет ни там, ни тут: их строк никто не считал.
    """
    rows = record.get("rows")
    if not isinstance(rows, dict):
        return ()
    return tuple(name for name, lines in rows.items() if len(lines or ()) >= _INDEXER_PAGE)


def beyond_first_circle(
    raw: list[RawResult],
    pictures: list[Picture],
    found: list[Picture],
    args: Args,
    name: str,
    index: int | None,
    config: Config,
    profile: Profile,
    capped: tuple[str, ...],
) -> list[str]:
    """Какие ступени :data:`BEYOND` боевой поиск взял бы на этом пуле (TC-416).

    Спрашиваются САМИ боевые гейты и в том же порядке, что в :func:`~torrcast.cli._search`
    (потолок - только там, где до него доходит очередь: после паспортного добора его не
    спрашивают). Пройти за ними щуп не может - за каждым стоит круг по индексерам, - но
    назвать их обязан: на этих запросах пул показа шире сохранённого, и «замерено на
    корпусе» тут значит «замерено до добора».
    """
    beyond: list[str] = []
    if not raw:
        beyond.append("раскладка")
    if index is not None and not found:
        beyond.append("цифра в имени")
    if worth_asking_original(found, args, config, profile):
        beyond.append("паспорт")
    elif index is None and _ceiling_hides_name(asked_nobody(capped), name, pictures, found):
        beyond.append("потолок")
    if _lacks_season(found, args):
        beyond.append("сезон")
    if voiceless_pool(found, args, config, profile) is not None:
        beyond.append("голос")
    return beyond


def asked_nobody(capped: tuple[str, ...]) -> Prowlarr:
    """Клиент, которого никто ни о чём не спрашивал: помнит только полные страницы.

    Гейт потолка (:func:`~torrcast.cli._ceiling_hides_name`) спрашивает у клиента ровно
    одно поле, и подделывать ради этого сам гейт нечего. Адреса у клиента нет намеренно:
    сходить им никуда нельзя, а щупу и не надо.
    """
    client = Prowlarr("", "")
    client.capped = capped
    return client


def verdicts(plan: _Plan, args: Args) -> tuple[list[int], dict[str, int]]:
    """Очередь кандидатов и приговоры ступеней по одной картине, со сверкой счёта.

    Сумма очереди и всех причин отсева обязана сойтись с пулом картины - так устроен
    :func:`queue_drops`. Сверка стоит тут, а не в глазах читателя: щуп, который сам
    теряет раздачи, мерить продукт не годится.
    """
    queue = plan.candidates(args)
    drops = queue_drops(plan, queue)
    total = len(queue) + sum(drops.values())
    if total != len(plan.picture.releases):
        raise ReplayMismatchError(
            f"«{plan.picture.title}»: очередь {len(queue)} + отсев {sum(drops.values())} "
            f"= {total}, а раздач у картины {len(plan.picture.releases)}"
        )
    return queue, drops


def release_verdicts(plan: _Plan, queue: list[int]) -> list[dict[str, Any]]:
    """Сиды и приговор каждой раздачи картины, без молчаливого остатка."""
    places = {number: place for place, number in enumerate(queue, start=1)}
    ranked = {id(release): number for number, release in enumerate(plan.ranked, start=1)}
    out: list[dict[str, Any]] = []
    for release in plan.picture.releases:
        number = ranked.get(id(release))
        place = places.get(number) if number is not None else None
        reason = None
        if number is None:
            reason = OFF_SEASON
        elif place is None:
            reason = drop_reason(release, plan)
        out.append(
            {
                "name": release.raw_name,
                "seeders": release.seeders,
                "size": release.size,
                "indexer": release.indexer,
                "queue": place,
                "drop_reason": reason,
            }
        )
    if sum(item["queue"] is not None for item in out) != len(queue):
        raise ReplayMismatchError(f"«{plan.picture.title}»: пораздачная очередь не сошлась с общей")
    return out


def size_of(release: Release) -> str:
    return f"{release.size / 1024**3:.1f} ГБ" if release.size else "размер не назван"


def name_of(picture: Picture) -> str:
    also = f" (+ «{picture.also}»)" if picture.also else ""
    return f"{picture.title} ({picture.year or 'год не назван'}, {picture.kind}){also}"


def brief(item: Replay) -> str:
    gates = "".join(("Т" if item.thin else "-", "Н" if item.unfit else "-"))
    # 🔴 TC-340. Верх меню - это ДЕФОЛТ: список печатается по планам, и картина с пустым
    # пулом отбора в него не попадает вовсе. Прежде колонка звала верхом первую картину
    # menu_order и дописывала «→ Enter: другая» - строку, которой человек не видел.
    default, above = item.default, item.above_default
    shown = name_of(default) if default is not None else "-"
    if above:
        more = f" и ещё {len(above) - 1}" if len(above) > 1 else ""
        shown += f"  · без плана и не в меню: {name_of(above[0])}{more}"
    return (
        f"{item.query:<28}{item.raw_rows:>6}{item.results:>7}{item.pictures:>7}"
        f"{len(item.menu):>6}{len(item.merges):>7}  {gates}  {shown}"
    )


def detail(item: Replay, menu_shown: int, releases_shown: int) -> list[str]:
    out = [
        f"\n=== {item.query} ===",
        f"строк выдачи {item.raw_rows} → раздач {item.results} · картин в каталоге "
        f"{item.pictures} · в меню {len(item.menu)} · пул тощий: "
        f"{'да' if item.thin else 'нет'} · пул негоден: {'да' if item.unfit else 'нет'}",
        f"за первым кругом (щуп не ходит): {', '.join(item.beyond) or 'нет'}",
    ]
    for members, picture in item.merges:
        names = " + ".join(
            f"«{p.title}» ({p.year or '?'}, раздач {len(p.releases)})" for p in members
        )
        out.append(
            f"склейка: {names} → «{picture.title}» ({picture.year or '?'}), "
            f"кучек {len(members)}, раздач {len(picture.releases)}"
        )
    args = Args(query=item.query.split())
    by_key = {plan.picture.key: plan for plan in item.plans}
    default = item.default
    number = 0
    for picture in item.menu[:menu_shown]:
        plan = by_key.get(picture.key)
        # Номер тут - тот же, что человек прочтёт на экране и назовёт в ответе, поэтому
        # считается он по планам: беспланная картина номера не получает вовсе (TC-340).
        number += plan is not None
        spot = f"{number}" if plan is not None else "-"
        mark = " ← Enter" if default is not None and picture.key == default.key else ""
        out.append(
            f"  [{spot}] {name_of(picture)} раздач {len(picture.releases)}, "
            f"строк {picture.rows}{mark}"
        )
        if plan is None:
            out.append("       пул отбора пуст: нужного сезона в раздачах нет - в меню её нет")
            continue
        queue, drops = verdicts(plan, args)
        gates = f"ворота {'открыты' if plan.loose else 'обычные'}"
        gates += ", последняя надежда открыта" if plan.last_resort else ""
        out.append(f"       очередь {len(queue)} из {len(picture.releases)} · {gates}")
        for place, number_in_plan in enumerate(queue[:releases_shown], start=1):
            release = plan.ranked[number_in_plan - 1]
            head = "дефолт" if place == 1 else f"запас {place - 1}"
            out.append(
                f"       {head} №{number_in_plan} {release.raw_name[:96]}"
                f"\n           {release.seeders} сид · {size_of(release)} · {release.indexer}"
            )
        if drops:
            told = " · ".join(f"{why} {count}" for why, count in sorted(drops.items()))
            out.append(f"       отсев: {told}")
    if len(item.menu) > menu_shown:
        out.append(f"  ... ещё картин в меню: {len(item.menu) - menu_shown}")
    if missed := item.missed:
        out.append(f"мимо меню (каталог знает, pick_franchise не пустил): {len(missed)}")
        for picture in missed:
            out.append(f"     - {name_of(picture)} раздач {len(picture.releases)}")
    return out


def glue_report(items: list[Replay]) -> list[str]:
    out = ["\n=== СКЛЕЙКИ ==="]
    total = 0
    for item in items:
        for members, picture in item.merges:
            total += 1
            names = " + ".join(f"«{p.title}» ({p.year or '?'}/{len(p.releases)})" for p in members)
            out.append(
                f"{item.query:<24} {names} → «{picture.title}» ({picture.year or '?'}), "
                f"кучек {len(members)}, раздач {len(picture.releases)}"
            )
    touched = sum(1 for item in items if item.merges)
    out.append(f"\nсклеек {total} на {touched} запросах из {len(items)}")
    return out


def beyond_report(items: list[Replay]) -> list[str]:
    """Чем пул щупа отличается от пула показа - списком и числами (TC-416).

    Строка на ступень: сколько запросов корпуса увели бы показ за второй круг. Это не
    приговор корпусу, а его паспорт: сравнивать два замера можно, только зная, у скольких
    запросов замеряли пул до добора, а не после.
    """
    out = ["\n=== ПУТИ ЗА ПЕРВЫМ КРУГОМ: ЩУП ИХ НЕ ХОДИТ ==="]
    for step, told in BEYOND.items():
        count = sum(1 for item in items if step in item.beyond)
        out.append(f"{step:<16}{count:>4} из {len(items)}  {told}")
    touched = sum(1 for item in items if item.beyond)
    out.append(f"\n{UNSEEN}")
    out.append(
        f"хотя бы одна ступень: {touched} из {len(items)} - на этих запросах показ искал бы "
        "дальше, а числа щупа сняты с первого круга"
    )
    return out


def as_json(item: Replay) -> dict[str, Any]:
    args = Args(query=item.query.split())
    top, default = item.top, item.default
    plans: list[dict[str, Any]] = []
    for plan in item.plans:
        queue, drops = verdicts(plan, args)
        chosen = plan.ranked[queue[0] - 1] if queue else None
        plans.append(
            {
                "title": plan.picture.title,
                "year": plan.picture.year,
                "kind": plan.picture.kind,
                "releases": len(plan.picture.releases),
                "rows": plan.picture.rows,
                "queue": len(queue),
                "loose": plan.loose,
                "last_resort": plan.last_resort,
                "drops": drops,
                "release_verdicts": release_verdicts(plan, queue),
                "default": None
                if chosen is None
                else {
                    "name": chosen.raw_name,
                    "seeders": chosen.seeders,
                    "size": chosen.size,
                    "indexer": chosen.indexer,
                },
            }
        )
    return {
        "query": item.query,
        "pool": item.pool,
        "raw_rows": item.raw_rows,
        "results": item.results,
        "pictures": item.pictures,
        "menu": len(item.menu),
        "missed": [
            {"title": p.title, "year": p.year, "releases": len(p.releases)} for p in item.missed
        ],
        "thin": item.thin,
        "unfit": item.unfit,
        "any_picture_playable": item.any_picture_playable,
        "default_is_menu_top": item.default_is_menu_top,
        "top": None
        if top is None
        else {
            "title": top.title,
            "year": top.year,
            "also": top.also,
            "releases": len(top.releases),
        },
        # Вид картины называется наравне с именем и годом: без него фильм и сериал
        # одного имени и года неразличимы, и счёт доступности сверяет их вслепую
        # (:func:`runreport.same_picture`).
        "default": None
        if default is None
        else {
            "title": default.title,
            "year": default.year,
            "kind": default.kind,
            "releases": len(default.releases),
        },
        "merges": [
            {
                "into": picture.title,
                "year": picture.year,
                "parts": len(members),
                "from": [
                    {"title": p.title, "year": p.year, "releases": len(p.releases)} for p in members
                ],
                "releases": len(picture.releases),
            }
            for members, picture in item.merges
        ],
        "plans": plans,
        "beyond": item.beyond,
    }


def asks_of(query: str, templates: list[str]) -> list[str]:
    """Какими запросами спрашивать сохранённый пул (``--ask``, TC-340).

    Без флага - тем единственным, которым пул снят. С флагом - каждым названным, и
    ``{}`` в нём заменяется снятым запросом: «тот же пул, другой номер части» пишется
    как ``--ask '{}' --ask '{} 2'`` и даёт пары, а не два несравнимых прогона. Ровно
    ради таких пар вокруг щупа трижды писали обвязку вне репы.
    """
    if not templates:
        return [query]
    return [template.replace("{}", query) for template in templates]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="офлайн-прогон отбора по сохранённым выдачам")
    ap.add_argument("pools", type=Path, help="pools.jsonl со снятыми выдачами индексеров")
    ap.add_argument(
        "--query",
        action="append",
        default=[],
        help="разобрать подробно только запросы, содержащие эту подстроку",
    )
    ap.add_argument(
        "--ask",
        action="append",
        default=[],
        metavar="ЗАПРОС",
        help="спросить пул НЕ тем запросом, которым он снят; {} - место снятого "
        "(--ask '{} 2'). Флаг повторяется: пул прогоняется каждым запросом подряд",
    )
    ap.add_argument("--glue", action="store_true", help="отчёт о склейках картин")
    ap.add_argument("--menu", type=int, default=5, help="сколько картин меню расписывать")
    ap.add_argument("--releases", type=int, default=3, help="сколько релизов очереди печатать")
    ap.add_argument("--jsonl", type=Path, help="куда положить разбор построчно")
    args = ap.parse_args(argv)
    cmdline = list(argv) if argv is not None else sys.argv[1:]

    config = tune(Config(), CAUTIOUS)
    items: list[Replay] = []
    for line in args.pools.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        query = str(record.get("query", ""))
        batches, capped = batches_of(record), capped_of(record)
        for asked in asks_of(query, args.ask):
            items.append(replay(asked, batches, config, CAUTIOUS, capped, pool=query))

    picked = (
        [
            item
            for item in items
            if any(needle.lower() in item.query.lower() for needle in args.query)
        ]
        if args.query
        else []
    )

    if picked:
        for item in picked:
            print("\n".join(detail(item, args.menu, args.releases)))
    else:
        print(
            f"{'запрос':<28}{'строк':>6}{'раздач':>7}{'картин':>7}{'меню':>6}{'склеек':>7}"
            f"  ТН  верх меню"
        )
        for item in items:
            print(brief(item))
        print(
            "\n  ТН: Т - пул тощий (строк за картиной < "
            f"{THIN_POOL}), Н - пул негоден (играть нечего)"
        )

    print("\n".join(beyond_report(picked or items)))

    if args.glue:
        print("\n".join(glue_report(picked or items)))

    if args.jsonl:
        with args.jsonl.open("w", encoding="utf-8") as fh:
            for item in items:
                fh.write(json.dumps(as_json(item), ensure_ascii=False) + "\n")
        card = runpass.passport("poolreplay", [args.pools], cmdline)
        print(f"\n{runpass.told(card)}\nпаспорт прогона: {runpass.write(card, args.jsonl)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
