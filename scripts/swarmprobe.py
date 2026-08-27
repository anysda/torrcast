#!/usr/bin/env python3
"""Замер класса «своя картина в меню есть, но её рой мёртв, а Enter уехал на чужую».

Инструмент разработчика: в устанавливаемый пакет не входит.

    python scripts/swarmprobe.py pools.jsonl --facts facts.json --canon canon.json \
        --profile q70d --jsonl out.jsonl

Живых служб не нужно ни одной: ни Prowlarr, ни справки, ни сети.

Предмет замера. Дефолт меню - первая по хронологии картина, чей рой ЖИВ
(:func:`~torrcast.usecases.choice.first_alive.first_alive`), а живость картины - сиды
лучшей из её ГОДНЫХ раздач (:func:`~torrcast.usecases.choice.liveliness.liveliness`)
против порога :data:`~torrcast.domain.rank_settings.ALIVE_SEEDERS`. Оба множителя тут
профильные: годность раздачи спрашивает кодеки и потолки ПРИЁМНИКА, поэтому одна и та же
картина на осторожном профиле бывает мертва, а на приставке жива. Числа между профилями
не переносятся, и щуп печатает профиль первой строкой.

Спрошенная картина - эталон корпуса (``--canon``: имя, вид, год на запрос), а не верх
меню; сверяется она ровно мерой :func:`anchorprobe.verdict_of` - по виду и году, а
бесстрочная - по привязке. Судить по имени нельзя: имена у половинок картины общие.

Каждый круг каждого запроса получает ровно один класс:

* ``та`` - по Enter идёт спрошенная картина;
* ``другая половина`` - идёт та же картина, но другой её половиной: сверка признаёт
  спрошенными обе, личность одна, а вот русская озвучка на этой развилке теряется;
* ``рой мёртв`` - спрошенная картина в меню ЕСТЬ, но её рой ниже порога, и Enter уехал
  на другую. Это и есть предмет карточки;
* ``обойдена живой`` - спрошенная картина в меню есть, порог живости прошла, а дефолта
  всё равно не взяла: её обошла другая ступень выбора, и лечится это не порогом роя;
* ``моей нет`` - спрошенной картины в меню нет вовсе: другой класс, к рою отношения не
  имеет;
* ``играть нечем`` - плана нет ни у одной картины меню;
* ``вне канона`` - эталона на этот запрос нет, и случай не судится.

Внутри класса ``рой мёртв`` разводятся две разные беды, и путать их нельзя:

* **чужой сезон** - каталог подписал взятую картину ТЕМ ЖЕ именем, что и спрошенную:
  человек просит один сезон, а играет соседний под тем же названием. Молчаливая подмена;
* **чужая вещь** - имя другое, и человек хотя бы видит в меню, что взяли не то.

Рядом печатается цена каждого продуктового исхода, и печатается числами:

* сколько раздач у спрошенной картины ЕСТЬ, сколько из них годных и каков их рой -
  этим меряется «ждать»: ждать нечего там, где живой раздачи нет вовсе;
* есть ли у спрошенной картины русская озвучка и есть ли она у взятой - озвучка стоит на
  лестнице продукта выше чёткости, и терять её молча нельзя;
* сказал ли выбор честную строку про смену картины
  (:func:`~torrcast.usecases.choice.default_note.default_note`) - без неё чужой сезон
  уезжает к зрителю под именем спрошенного.

⚠️ Щуп ходит первый круг плюс сохранённые пулы добора: там, где боевой поиск ушёл бы
дальше (печатается последней строкой), любое число этого замера - оценка снизу.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import anchorprobe
import poolreplay
import runpass
import widenreplay
from probeprofile import add_argument as add_profile_argument
from probeprofile import choose as choose_profile

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.runtime.wire import wire
from torrcast.usecases.choice.configure import _environment_port
from torrcast.usecases.choice.default_note import default_note
from torrcast.usecases.choice.liveliness import liveliness
from torrcast.usecases.select.plan import Plan

#: Классы случая. Один круг одного запроса получает ровно один из них.
SAME = "та"
HALF = "другая половина"
DEAD = "рой мёртв"
PASSED = "обойдена живой"
ABSENT = "моей нет"
NOTHING = "играть нечем"
UNMARKED = "вне канона"
CLASSES = (SAME, HALF, DEAD, PASSED, ABSENT, NOTHING, UNMARKED)

#: Чем разведён класс :data:`DEAD` внутри себя.
KIN = "чужой сезон"
STRANGER = "чужая вещь"


@dataclass(slots=True)
class Case:
    """Один круг одного запроса: чей рой решил дело и чего этот приговор стоил."""

    query: str
    scope: str
    verdict: str = UNMARKED
    #: Спрошенная картина: имя, год, вид. ``None`` - её в меню нет.
    mine: list[Any] | None = None
    #: Рой спрошенной картины той же меркой, что у выбора: сиды лучшей ГОДНОЙ раздачи.
    mine_alive: int = 0
    #: Раздач у спрошенной картины всего и в очереди отбора.
    mine_releases: int = 0
    mine_ranked: int = 0
    #: Самый большой рой среди ВСЕХ её раздач - потолок того, что даст ожидание.
    mine_top: int = 0
    mine_dubbed: bool = False
    #: Картина, которая пойдёт по Enter, и её же числа.
    played: list[Any] | None = None
    played_alive: int = 0
    played_dubbed: bool = False
    #: Каталог подписал взятую картину тем же именем, что и спрошенную.
    kin: bool = False
    #: Честная строка выбора про смену картины; пусто - выбор промолчал.
    note: str = ""


def _told(picture: Picture | None) -> list[Any] | None:
    """Личность картины одной строкой: имя, год, вид."""
    return None if picture is None else [picture.title, picture.year, picture.kind]


def _dubbed(picture: Picture) -> bool:
    """Есть ли у картины хоть одна раздача с русским звуком."""
    return any(release.dubbed for release in picture.releases)


def _mine_plan(plans: list[Plan], canon: dict[str, Any] | None) -> Plan | None:
    """План спрошенной картины: самый живой из тех, что сверка признала спрошенными."""
    mine = [
        plan for plan in plans if anchorprobe.verdict_of(plan.picture, canon) == anchorprobe.SAME
    ]
    return max(mine, key=liveliness) if mine else None


def _mine_picture(menu: list[Picture], canon: dict[str, Any] | None) -> Picture | None:
    """Спрошенная картина в меню - даже если очередь отбора у неё пуста и плана нет."""
    mine = [one for one in menu if anchorprobe.verdict_of(one, canon) == anchorprobe.SAME]
    return max(mine, key=lambda one: len(one.releases)) if mine else None


def _verdict(
    played: Picture | None, picture: Picture | None, canon: dict[str, Any] | None, alive: int
) -> str:
    """Класс случая: лестница вопросов, где каждый ответ отменяет все следующие."""
    if played is None:
        return NOTHING
    if anchorprobe.verdict_of(played, canon) == anchorprobe.SAME:
        # Половинки одной картины сверка признаёт спрошенными обе, и подменой это не
        # является: личность та же. Но половина, которую взяли, бывает беднее той, что
        # осталась, - и потерю русского голоса на этой развилке видно только счётом.
        return SAME if picture is not None and played.key == picture.key else HALF
    if picture is None:
        return ABSENT
    return DEAD if alive < _environment_port().alive_seeders else PASSED


def case_of(query: str, circle: anchorprobe.Circle, canon: dict[str, Any] | None) -> Case:
    """Разобрать один круг одного запроса в один класс - и приложить его цену."""
    out = Case(query=query, scope=circle.scope)
    played = anchorprobe.default_of(circle.plans)
    out.played = _told(played)
    if played is not None:
        out.played_dubbed = _dubbed(played)
        for one in circle.plans:
            if one.picture.key == played.key:
                out.played_alive = liveliness(one)
    if canon is None:
        return out
    plan = _mine_plan(circle.plans, canon)
    picture = plan.picture if plan is not None else _mine_picture(circle.menu, canon)
    if plan is not None:
        out.mine_alive, out.mine_ranked = liveliness(plan), len(plan.ranked)
    if picture is not None:
        out.mine = _told(picture)
        out.mine_releases = len(picture.releases)
        out.mine_top = max((release.seeders for release in picture.releases), default=0)
        out.mine_dubbed = _dubbed(picture)
        out.kin = played is not None and played.title.casefold() == picture.title.casefold()
    out.verdict = _verdict(played, picture, canon, out.mine_alive)
    if out.verdict in (DEAD, PASSED, ABSENT, HALF):
        out.note = default_note(circle.plans, circle.asked)
    return out


def tally(rows: list[Case], scope: str) -> dict[str, int]:
    """Сколько случаев каждого класса на одном круге."""
    mine = [row for row in rows if row.scope == scope]
    return {name: sum(row.verdict == name for row in mine) for name in CLASSES}


def dead_rows(rows: list[Case], scope: str) -> list[Case]:
    """Случаи предмета карточки на одном круге, самые мёртвые сверху."""
    found = [row for row in rows if row.scope == scope and row.verdict == DEAD]
    return sorted(found, key=lambda row: (row.mine_top, row.query))


def prices(found: list[Case]) -> dict[str, int]:
    """Цена каждого продуктового исхода на разобранном классе - числами, без выбора."""
    alive = _environment_port().alive_seeders
    return {
        "всего": len(found),
        KIN: sum(row.kin for row in found),
        STRANGER: sum(not row.kin for row in found),
        "взятая жива": sum(row.played_alive >= alive for row in found),
        "строка есть": sum(bool(row.note) for row in found),
        "молча": sum(not row.note for row in found),
        "ждать нечего": sum(row.mine_top == 0 for row in found),
        "ждать есть чего": sum(row.mine_top > 0 for row in found),
        "своя годна, но тиха": sum(row.mine_ranked > 0 and row.mine_alive == 0 for row in found),
        "теряется озвучка": sum(row.mine_dubbed and not row.played_dubbed for row in found),
    }


def report(rows: list[Case], beyond: int) -> None:
    """Печать замера: тали классов по кругам, разбор предмета и цена исходов."""
    alive = _environment_port().alive_seeders
    print(f"порог живости роя: {alive} сид(ов)")
    for scope in sorted({row.scope for row in rows}):
        counted = tally(rows, scope)
        told = ", ".join(f"{name} {count}" for name, count in counted.items() if count)
        print(f"\nкруг «{scope}»: запросов {sum(counted.values())}; {told}")
        halves = [row for row in rows if row.scope == scope and row.verdict == HALF]
        for row in halves:
            lost = row.mine_dubbed and not row.played_dubbed
            print(
                f"  половина: «{row.query}» {row.mine} рой {row.mine_alive} -> "
                f"{row.played} рой {row.played_alive}: "
                f"{'русская озвучка ТЕРЯЕТСЯ' if lost else 'озвучка на месте'}"
            )
        found = dead_rows(rows, scope)
        if not found:
            print("  предмета карточки на этом круге нет ни одного")
            continue
        header = (
            f"  {'запрос':<26}{'своя':<34}{'рой':>5}{'всего':>6}{'очер':>5}{'верх':>5}  "
            f"{'взято':<34}{'рой':>5}{'вид':>12}"
        )
        print(header)
        for row in found:
            mine = f"{row.mine[0]} ({row.mine[1]})" if row.mine else "-"
            took = f"{row.played[0]} ({row.played[1]})" if row.played else "-"
            print(
                f"  {row.query:<26}{mine[:33]:<34}{row.mine_alive:>5}{row.mine_releases:>6}"
                f"{row.mine_ranked:>5}{row.mine_top:>5}  {took[:33]:<34}{row.played_alive:>5}"
                f"{(KIN if row.kin else STRANGER):>12}"
            )
        for name, count in prices(found).items():
            print(f"    {name}: {count}")
        for row in found:
            print(f"    «{row.query}» строка: {row.note or 'ВЫБОР ПРОМОЛЧАЛ'}")
    print(
        f"\n⚠️ боевой поиск ушёл бы за первый круг у {beyond} запросов - "
        "по ним любое число выше оценка снизу"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pools", type=Path, help="сохранённые выдачи, JSONL")
    parser.add_argument("--facts", type=Path, default=None, help="кэш справки, JSON")
    parser.add_argument("--canon", type=Path, default=None, help="эталон корпуса, JSON")
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
    canon: dict[str, Any] = {}
    if args.canon is not None:
        canon = {str(row["query"]): row for row in json.loads(args.canon.read_text("utf-8"))}
    ask = widenreplay.facts_passport(args.facts)
    rows: list[Case] = []
    mismatches: list[str] = []
    beyond = 0
    for query in order:
        found, broken, steps = anchorprobe.menus_of(
            query, records[query], pools, config, profile, ask
        )
        rows.extend(case_of(query, one, canon.get(query)) for one in found)
        mismatches.extend(broken)
        beyond += bool(steps)
    if mismatches:
        for note in mismatches:
            print(f"СЧЁТ НЕ СОШЁЛСЯ: {note}", file=sys.stderr)
        return 1
    report(rows, beyond)
    if args.jsonl is not None:
        with args.jsonl.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
        card = runpass.passport("swarmprobe", [args.pools], sys.argv[1:])
        print(f"\n{runpass.told(card)}\nпаспорт прогона: {runpass.write(card, args.jsonl)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
