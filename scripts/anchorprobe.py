#!/usr/bin/env python3
"""Замер привязки бесстрочных картин по разобранному оригиналу на сохранённых выдачах.

Инструмент разработчика: в устанавливаемый пакет не входит.

    python scripts/anchorprobe.py pools.jsonl --facts facts.json --canon canon.json \
        --jsonl out.jsonl
    python scripts/anchorprobe.py pools.jsonl --facts facts.json --canon canon.json \
        --base base.jsonl

Живых служб не нужно ни одной: ни Prowlarr, ни справки, ни сети.

Предмет замера. Латинская половина картины года не несёт, и порядок меню ставит её в
хвост - позади датированных соседей по франшизе. Дефолт («первая живая по хронологии»)
садится тогда на датированный спин-офф, хотя спрошенная картина жива и стоит в том же
меню. Разводит их разобранное каталогом поле: русская половина несёт ``original`` -
ровную подпись латинской картины, а спин-офф оригиналом не назван никем. Привязка
(:func:`torrcast.domain.anchor_years.anchor_years`) даёт бесстрочной картине год той, чей
оригинал зовёт её по имени, - и порядок меню перестаёт её прятать.

Меряется разлёт этой привязки на ДВУХ кругах каждого запроса:

* **первый** - ровно боевой тракт отбора первого круга (:func:`poolreplay.replay`);
* **добор** - меню после добора по второму имени той же меркой, что у
  ``widenreplay``: где добор взят - итог самого захода, где гейт отверг - контрфакт
  «что он привёз бы» (гейт счёта картин этот щуп НЕ трогает и не снимает).

Верность обоих кругов сверяется с самим ``widenreplay``: картина по Enter, посчитанная
щупом, обязана совпасть с его ``plays`` по обеим сторонам - иначе щуп мерит не тот
показ, и об этом сказано вслух, а не молча.

Ответ - четыре числа на каждый круг (с ``--base``, против прогона до правки):

* сколько дефолтов сменилось (личность картины: имя, год, вид);
* сколько подмен УШЛО (дефолт стоял не на спрошенной картине, а встал на неё);
* сколько подмен ПРИШЛО (было на спрошенной - уехало); 🔴 не ноль - не выкатывать;
* у скольких пропала русская озвучка (у взятой картины не осталось раздачи с русским
  звуком - :attr:`torrcast.domain.release.Release.dubbed`).

Спрошенная картина - это эталон корпуса (``--canon``: имя, вид, год на запрос), а не
верх меню. Бесстрочная картина считается спрошенной, когда её привязка - канонный год;
бесстрочная без привязки автоматически не судится - такие случаи печатаются списком и
решаются глазами.

Рядом считаются стражи выбора (:func:`certain_default`, :func:`part_one_swap`,
:func:`named_elsewhere`, :func:`namesake_take`, :func:`default_note`): ни один не
должен быть перебит молча, и каждый переход «стрелял - замолчал» печатается с именем
запроса и тем, куда переехал дефолт.

⚠️ Щуп ходит только первый круг плюс сохранённые пулы добора: там, где боевой поиск
ушёл бы дальше (печатается последней строкой), любое число этого замера - оценка снизу.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import poolreplay
import runpass
import widenreplay
from probeprofile import add_argument as add_profile_argument
from probeprofile import choose as choose_profile

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.prowlarr.merge import merge
from torrcast.adapters.prowlarr.to_releases import to_releases
from torrcast.domain.args import Args
from torrcast.domain.cluster import cluster
from torrcast.domain.config import Config
from torrcast.domain.menu_order import menu_order
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture
from torrcast.domain.profile import Profile
from torrcast.domain.raw_result import RawResult
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.runtime.wire import wire
from torrcast.usecases.choice.certain_default import certain_default
from torrcast.usecases.choice.default_note import default_note
from torrcast.usecases.choice.first_alive import first_alive
from torrcast.usecases.choice.named_elsewhere import named_elsewhere
from torrcast.usecases.choice.namesake_take import namesake_take
from torrcast.usecases.choice.part_one_swap import part_one_swap
from torrcast.usecases.discover._second_language import _second_language
from torrcast.usecases.discover.season_reread import season_reread
from torrcast.usecases.reinforce.plan_for import plan_for
from torrcast.usecases.select.plan import Plan

#: Вердикты сверки дефолта с эталоном корпуса.
SAME, OTHER, UNSURE, NONE, UNMARKED = "та", "ДРУГАЯ", "?", "нет", "вне канона"


@dataclass(slots=True)
class Scope:
    """Что играет по Enter на одном круге одного запроса - и что сказали стражи."""

    query: str
    scope: str
    played: list[Any] | None = None
    anchor: int | None = None
    dubbed: bool = False
    verdict: str = UNMARKED
    guards: dict[str, Any] = field(default_factory=dict)


def plans_of(menu: list[Picture], args: Args, config: Config, profile: Profile) -> list[Plan]:
    """Планы картин меню - тем же счётом, что у показа."""
    ranked = (plan_for(picture, args, config, profile) for picture in menu)
    return [plan for plan in ranked if plan.ranked]


def default_of(plans: list[Plan]) -> Picture | None:
    """Картина, которая пойдёт по Enter: первая живая по хронологии."""
    return plans[first_alive(plans) - 1].picture if plans else None


def guards_of(plans: list[Plan], asked: str) -> dict[str, Any]:
    """Что сказали стражи выбора на этом меню - все и поимённо."""
    if not plans:
        return {}
    return {
        "certain": certain_default(plans, asked),
        "part_one_swap": part_one_swap(plans, asked),
        "named_elsewhere": named_elsewhere(plans, asked),
        "namesake_take": namesake_take(plans),
        "default_note": default_note(plans, asked),
    }


def verdict_of(played: Picture | None, canon: dict[str, Any] | None) -> str:
    """Та ли картина играет, что спросили; эталон - канон корпуса (вид и год).

    Бесстрочная картина года не несёт, и сверять её с каноном можно лишь привязкой:
    привязана к канонному году - это та картина; не привязана - щуп не судит, случай
    уходит в печатный список и решается глазами. Судить её по имени нельзя: имена у
    половинок общие, и «знакомое имя» тут было бы догадкой, а не разбором.
    """
    if played is None:
        return NONE
    if canon is None:
        return UNMARKED
    if played.kind != canon["kind"]:
        return OTHER
    if played.year == canon["year"]:
        return SAME
    if played.year is None:
        # До правки поля ``anchor`` у картины нет вовсе - читается оно мягко, и
        # бесстрочная без привязки уходит в печатный список, а не в счёт.
        return SAME if getattr(played, "anchor", None) == canon["year"] else UNSURE
    return OTHER


def told(played: Picture | None) -> list[Any] | None:
    """Личность картины одной строкой: имя, год, вид - этим и сверяется смена дефолта."""
    if played is None:
        return None
    return [played.title, played.year, played.kind]


def told_as_widen(played: Picture | None) -> list[Any] | None:
    """Та же картина в записи ``widenreplay.told`` - для сверки с его ``plays``."""
    if played is None:
        return None
    return [played.title, played.year, len(played.releases)]


def scope_of(
    query: str, scope: str, plans: list[Plan], asked: str, canon: dict[str, Any] | None
) -> Scope:
    played = default_of(plans)
    return Scope(
        query=query,
        scope=scope,
        played=told(played),
        anchor=None if played is None else getattr(played, "anchor", None),
        dubbed=played is not None and any(r.dubbed for r in played.releases),
        verdict=verdict_of(played, canon),
        guards=guards_of(plans, asked),
    )


@dataclass(slots=True)
class Circle:
    """Меню одного круга одного запроса - и то, чем это меню считали."""

    scope: str
    plans: list[Plan]
    menu: list[Picture]
    catalog: list[Picture]
    args: Args
    asked: str


def menus_of(
    query: str,
    record: dict[str, Any],
    pools: dict[str, list[list[RawResult]]],
    config: Config,
    profile: Profile,
    ask: Any,
) -> tuple[list[Circle], list[str], list[str]]:
    """Меню обоих кругов одного запроса: первый боевой тракт и меню после добора.

    Вторая половина - ровно переигровка ``widenreplay``: те же вызовы боевого кода,
    но с картинами в руках (щупам нужны озвучка, рой и привязка, а не только личность).
    Честность переигровки доказывается сверкой обеих картин по Enter с ``plays``
    самого ``widenreplay`` - расхождение названо строкой и счёт идти не может.

    Третий выход - ступени за первым кругом (:data:`poolreplay.BEYOND`): на таких
    запросах пул показа шире пула щупа, и числа по ним - оценка снизу.
    """
    mismatches: list[str] = []
    batches = poolreplay.batches_of(record)
    item = poolreplay.replay(query, batches, config, profile, poolreplay.capped_of(record))
    args = Args(query=query.split())
    asked = args.title_query
    name, index = split_franchise_index(asked)
    # Ровно порядок щупа добора: он спрашивает франшизу без расстановки меню, и строка
    # запроса читается сезоном той же функцией, что на боевом круге.
    found = pick_franchise(asked, item.catalog)
    if (reread := season_reread(args, name, index, found, item.catalog)) is not None:
        args, asked = reread, name
    out = [Circle("первый", item.plans, item.menu, item.catalog, args, asked)]

    row = widenreplay.widen(query, pools, config, profile, ask)
    if told_as_widen(item.default) != row.plays["до"]:
        mismatches.append(f"{query}: первый круг со щупом добора не сошёлся")
    if not (row.worth and row.alt and not row.missed):
        return out, mismatches, item.beyond

    raw = merge(*batches)
    client, said = widenreplay.SavedIndexer(pools), widenreplay.Quiet()
    merged, pictures, wider = _second_language(client, asked, args, raw, found, said, passport=ask)
    if len(merged) != len(raw):
        menu, catalog = menu_order(wider), pictures
    else:
        # Гейт отверг - контрфакт: та же вторая выдача, склеенная тем же кодом.
        second = client.given.get(row.alt.strip().casefold(), [])
        catalog = cluster(to_releases(merge(raw, second))) if second else item.catalog
        menu = menu_order(pick_franchise(asked, catalog))
    plans = plans_of(menu, args, config, profile)
    if told_as_widen(default_of(plans)) != row.plays["после"]:
        mismatches.append(f"{query}: круг добора со щупом не сошёлся")
    out.append(Circle("добор", plans, menu, catalog, args, asked))
    return out, mismatches, item.beyond


def circles(
    query: str,
    record: dict[str, Any],
    pools: dict[str, list[list[RawResult]]],
    config: Config,
    profile: Profile,
    ask: Any,
    canon: dict[str, Any] | None,
) -> tuple[list[Scope], list[str], list[str]]:
    """Что играет по Enter на обоих кругах одного запроса - и что сказали стражи."""
    found, mismatches, beyond = menus_of(query, record, pools, config, profile, ask)
    out = [scope_of(query, one.scope, one.plans, one.asked, canon) for one in found]
    return out, mismatches, beyond


def diff(base: list[Scope], rows: list[Scope]) -> dict[str, Any]:
    """Четыре числа разлёта против прогона до правки, по каждому кругу отдельно."""
    before = {(row.query, row.scope): row for row in base}
    out: dict[str, Any] = {}
    for scope in sorted({row.scope for row in rows}):
        changed: list[dict[str, Any]] = []
        gone = came = voiceless = 0
        guard_notes: list[str] = []
        for row in rows:
            if row.scope != scope or (old := before.get((row.query, row.scope))) is None:
                continue
            if old.played == row.played and old.guards == row.guards:
                continue
            if old.played != row.played:
                changed.append(
                    {
                        "запрос": row.query,
                        "было": old.played,
                        "стало": row.played,
                        "вердикт": f"{old.verdict} -> {row.verdict}",
                        "озвучка": f"{old.dubbed} -> {row.dubbed}",
                    }
                )
                gone += old.verdict == OTHER and row.verdict == SAME
                came += old.verdict == SAME and row.verdict == OTHER
                voiceless += bool(old.dubbed and not row.dubbed)
            for name, said in row.guards.items():
                if old.guards.get(name) != said:
                    guard_notes.append(f"{row.query}: {name}: {old.guards.get(name)!r} -> {said!r}")
        out[scope] = {
            "сменилось": len(changed),
            "подмен ушло": gone,
            "ПОДМЕН ПРИШЛО": came,
            "пропала озвучка": voiceless,
            "смены": changed,
            "стражи": guard_notes,
        }
    return out


def report(rows: list[Scope], summary: dict[str, Any] | None, beyond: int) -> None:
    """Печать замера: тали по кругам, а с базой - четыре числа и переходы стражей."""
    for scope in sorted({row.scope for row in rows}):
        mine = [row for row in rows if row.scope == scope]
        tally: dict[str, int] = {}
        for row in mine:
            tally[row.verdict] = tally.get(row.verdict, 0) + 1
        told_tally = ", ".join(f"{name} {count}" for name, count in sorted(tally.items()))
        print(f"круг «{scope}»: запросов {len(mine)}; {told_tally}")
    if summary is not None:
        for scope, numbers in summary.items():
            print(
                f"\nкруг «{scope}»: сменилось дефолтов {numbers['сменилось']}, "
                f"подмен ушло {numbers['подмен ушло']}, "
                f"ПОДМЕН ПРИШЛО {numbers['ПОДМЕН ПРИШЛО']}, "
                f"пропала русская озвучка у {numbers['пропала озвучка']}"
            )
            for change in numbers["смены"]:
                print(
                    f"  {change['запрос']}: {change['было']} -> {change['стало']} "
                    f"({change['вердикт']}; озвучка {change['озвучка']})"
                )
            for note in numbers["стражи"]:
                print(f"  страж: {note}")
    unsure = [row for row in rows if row.verdict == UNSURE]
    if unsure:
        print("\nбесстрочные без привязки - решаются глазами, не счётом:")
        for row in unsure:
            print(f"  {row.query} [{row.scope}]: {row.played}")
    print(
        f"\n⚠️ боевой поиск ушёл бы за первый круг у {beyond} запросов - "
        "по ним любое число выше оценка снизу"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pools", type=Path, help="сохранённые выдачи, JSONL")
    parser.add_argument("--facts", type=Path, default=None, help="кэш справки, JSON")
    parser.add_argument("--canon", type=Path, default=None, help="эталон корпуса, JSON")
    parser.add_argument("--base", type=Path, default=None, help="прогон до правки, JSONL")
    parser.add_argument("--jsonl", type=Path, default=None, help="куда сложить разбор")
    add_profile_argument(parser)
    args = parser.parse_args(argv)
    wire()
    config, choice = choose_profile(load_config(), args.profile)
    profile = choice.profile
    pools: dict[str, list[list[RawResult]]] = {}
    records: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for line in args.pools.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        pools[str(record["query"]).strip().casefold()] = poolreplay.batches_of(record)
        records[str(record["query"])] = record
        order.append(str(record["query"]))
    canon = {}
    if args.canon is not None:
        canon = {str(row["query"]): row for row in json.loads(args.canon.read_text("utf-8"))}
    ask = widenreplay.facts_passport(args.facts)
    rows: list[Scope] = []
    mismatches: list[str] = []
    beyond = 0
    for query in order:
        found, broken, steps = circles(
            query, records[query], pools, config, profile, ask, canon.get(query)
        )
        rows.extend(found)
        mismatches.extend(broken)
        beyond += bool(steps)
    if mismatches:
        for note in mismatches:
            print(f"СЧЁТ НЕ СОШЁЛСЯ: {note}", file=sys.stderr)
        return 1
    base: list[Scope] = []
    if args.base is not None:
        base = [
            Scope(**json.loads(line))
            for line in args.base.read_text("utf-8").splitlines()
            if line.strip()
        ]
    report(rows, diff(base, rows) if base else None, beyond)
    if args.jsonl is not None:
        with args.jsonl.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
        card = runpass.passport("anchorprobe", [args.pools], sys.argv[1:])
        print(f"\n{runpass.told(card)}\nпаспорт прогона: {runpass.write(card, args.jsonl)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
