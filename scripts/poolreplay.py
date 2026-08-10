#!/usr/bin/env python3
"""Офлайн-прогон боевого отбора по СОХРАНЁННЫМ выдачам индексеров.

Инструмент разработчика: в устанавливаемый пакет не входит.

    python scripts/poolreplay.py pools.jsonl
    python scripts/poolreplay.py pools.jsonl --query титаник
    python scripts/poolreplay.py pools.jsonl --glue
    python scripts/poolreplay.py pools.jsonl --jsonl out.jsonl

Живых служб не нужно ни одной: ни Prowlarr, ни TorrServer, ни приёмника, ни сети.
Выдачи в репе не лежат - путь к ним задаётся аргументом.

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

from torrcast.cli import (
    Args,
    _Plan,
    _plan_for,
    first_alive,
    queue_drops,
    unfit_pool,
)
from torrcast.parse import (
    THIN_POOL,
    Picture,
    Release,
    cluster,
    menu_order,
    pick_franchise,
)
from torrcast.profile import CAUTIOUS, Profile, tune
from torrcast.search import RawResult, merge, to_releases
from torrcast.state import Config

#: Что склеили и во что: список исходных кучек и получившаяся из них картина.
Merge = tuple[list[Picture], Picture]


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
        """Что играет по Enter: первая по хронологии живая часть (:func:`first_alive`).

        Верх списка и дефолт - разные вещи, и путать их нельзя: в меню «мумия» первой
        строкой стоит «Мумия» 1932 года, а Enter играет 1999-й.
        """
        return self.plans[first_alive(self.plans) - 1].picture if self.plans else None


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


def replay(query: str, batches: list[list[RawResult]], config: Config, profile: Profile) -> Replay:
    """Прогнать один пул по боевому тракту отбора."""
    args = Args(query=query.split())
    raw = merge(*batches) if batches else []
    with watching_glue() as merges:
        pictures = cluster(to_releases(raw))
    found = menu_order(pick_franchise(args.title_query, pictures))
    plans = [p for p in (_plan_for(pic, args, config, profile) for pic in found) if p.ranked]
    return Replay(
        query=query,
        raw_rows=sum(len(b) for b in batches),
        results=len(raw),
        catalog=pictures,
        menu=found,
        plans=plans,
        merges=merges,
        thin=max((p.rows for p in found), default=0) < THIN_POOL,
        unfit=bool(found) and unfit_pool(found, args, config, profile),
    )


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


def size_of(release: Release) -> str:
    return f"{release.size / 1024 ** 3:.1f} ГБ" if release.size else "размер не назван"


def name_of(picture: Picture) -> str:
    also = f" (+ «{picture.also}»)" if picture.also else ""
    return f"{picture.title} ({picture.year or 'год не назван'}, {picture.kind}){also}"


def brief(item: Replay) -> str:
    gates = "".join(("Т" if item.thin else "-", "Н" if item.unfit else "-"))
    top, default = item.top, item.default
    shown = name_of(top) if top else "-"
    if default is not None and (top is None or default.key != top.key):
        shown += f"  → Enter: {name_of(default)}"
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
    for number, picture in enumerate(item.menu[:menu_shown], start=1):
        mark = " ← Enter" if default is not None and picture.key == default.key else ""
        out.append(f"  [{number}] {name_of(picture)} раздач {len(picture.releases)}, "
                   f"строк {picture.rows}{mark}")
        plan = by_key.get(picture.key)
        if plan is None:
            out.append("       пул отбора пуст: нужного сезона в раздачах нет")
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


def as_json(item: Replay) -> dict[str, Any]:
    args = Args(query=item.query.split())
    top, default = item.top, item.default
    plans: list[dict[str, Any]] = []
    for plan in item.plans:
        queue, drops = verdicts(plan, args)
        chosen = plan.ranked[queue[0] - 1] if queue else None
        plans.append({
            "title": plan.picture.title,
            "year": plan.picture.year,
            "kind": plan.picture.kind,
            "releases": len(plan.picture.releases),
            "rows": plan.picture.rows,
            "queue": len(queue),
            "loose": plan.loose,
            "last_resort": plan.last_resort,
            "drops": drops,
            "default": None if chosen is None else {
                "name": chosen.raw_name, "seeders": chosen.seeders, "size": chosen.size,
                "indexer": chosen.indexer,
            },
        })
    return {
        "query": item.query,
        "raw_rows": item.raw_rows,
        "results": item.results,
        "pictures": item.pictures,
        "menu": len(item.menu),
        "missed": [
            {"title": p.title, "year": p.year, "releases": len(p.releases)} for p in item.missed
        ],
        "thin": item.thin,
        "unfit": item.unfit,
        "top": None if top is None else {"title": top.title, "year": top.year,
                                         "also": top.also, "releases": len(top.releases)},
        "default": None if default is None else {"title": default.title, "year": default.year,
                                                 "releases": len(default.releases)},
        "merges": [
            {"into": picture.title, "year": picture.year, "parts": len(members),
             "from": [{"title": p.title, "year": p.year, "releases": len(p.releases)}
                      for p in members],
             "releases": len(picture.releases)}
            for members, picture in item.merges
        ],
        "plans": plans,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="офлайн-прогон отбора по сохранённым выдачам")
    ap.add_argument("pools", type=Path, help="pools.jsonl со снятыми выдачами индексеров")
    ap.add_argument("--query", action="append", default=[],
                    help="разобрать подробно только запросы, содержащие эту подстроку")
    ap.add_argument("--glue", action="store_true", help="отчёт о склейках картин")
    ap.add_argument("--menu", type=int, default=5, help="сколько картин меню расписывать")
    ap.add_argument("--releases", type=int, default=3, help="сколько релизов очереди печатать")
    ap.add_argument("--jsonl", type=Path, help="куда положить разбор построчно")
    args = ap.parse_args(argv)

    config = tune(Config(), CAUTIOUS)
    items: list[Replay] = []
    for line in args.pools.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        query = str(record.get("query", ""))
        items.append(replay(query, batches_of(record), config, CAUTIOUS))

    picked = [
        item for item in items
        if any(needle.lower() in item.query.lower() for needle in args.query)
    ] if args.query else []

    if picked:
        for item in picked:
            print("\n".join(detail(item, args.menu, args.releases)))
    else:
        print(f"{'запрос':<28}{'строк':>6}{'раздач':>7}{'картин':>7}{'меню':>6}{'склеек':>7}"
              f"  ТН  верх меню")
        for item in items:
            print(brief(item))
        print("\n  ТН: Т - пул тощий (строк за картиной < "
              f"{THIN_POOL}), Н - пул негоден (играть нечего)")

    if args.glue:
        print("\n".join(glue_report(picked or items)))

    if args.jsonl:
        with args.jsonl.open("w", encoding="utf-8") as fh:
            for item in items:
                fh.write(json.dumps(as_json(item), ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
