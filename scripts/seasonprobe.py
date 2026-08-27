#!/usr/bin/env python3
"""Замер молчаливой подмены СЕЗОНА: спросили первый, а по Enter идёт соседний.

Инструмент разработчика: в устанавливаемый пакет не входит.

    python scripts/seasonprobe.py pools.jsonl --facts facts.json --jsonl out.jsonl
    python scripts/seasonprobe.py pools.jsonl --facts facts.json --base before.jsonl

Живых служб не нужно ни одной: ни Prowlarr, ни справки, ни сети.

Предмет замера. Разбор имени решает не только ВИД картины, но и её номер части, а номер
части у сериала и есть номер сезона (:func:`~torrcast.usecases.choice.asked_season.asked_season`).
Значит одна и та же правка разбора двигает две разные мерки, и мерить их порознь нельзя:
щуп вида (``kindprobe``) честно показывает ноль пришедших подмен ровно тогда, когда сезон
уже сполз. Здесь считается вторая половина - на тех же сохранённых выдачах и на обоих
кругах каждого запроса (:func:`anchorprobe.menus_of`).

Судятся только запросы, назвавшие серию вслух (``s1e1``): там сезон сказан человеком, и
сверять есть с чем. Остальные получают класс ``сезона не спрашивали`` и в счёт подмен не
идут.

Сезон, который зритель получит, решают ровно два звена, и щуп спрашивает оба по порядку.

**Первое - голова очереди отбора**: та раздача, которую показ потрогает первой. Очередь уже
отсеяна по :func:`~torrcast.usecases.rank.misses_episode.misses_episode`, поэтому раздача,
НАЗВАВШАЯ сезон, называет ровно спрошенный (:meth:`~torrcast.domain.release.Release.covers`):
пак ``[S01-06]`` на просьбу ``s5e2`` - правильная раздача, а не подмена, и судить её нечем.

**Второе - подпись картины**, и работает оно там, где имя раздачи о сезоне МОЛЧИТ. Сезон
файлам такой раздачи раздаёт :func:`~torrcast.domain.map_episodes.map_episodes` с пустой
подсказкой, то есть первым; настоящий же её сезон говорит только личность картины -
:attr:`~torrcast.domain.picture.Picture.part`, номер части, а у сериала номер части и есть
номер сезона. Часть названа чужим числом - зритель получит чужой сезон и не узнает об этом.

Класс случая:

* ``тот`` - голова назвала спрошенный сезон, либо молчит, а картина чужой части не носит;
* ``ЧУЖОЙ`` - голова о сезоне молчит, а картина подписана ДРУГОЙ частью;
  🔴 это и есть предмет карточки;
* ``не сериал`` - по Enter идёт картина без очереди серий: спросили сезон, играет фильм.
  Это беда ВИДА, её меряет ``kindprobe``, и в счёт сезонов она не идёт;
* ``играть нечем`` - плана нет ни у одной картины меню.

Рядом с каждым ``ЧУЖОЙ`` печатается честная строка выбора
(:func:`~torrcast.usecases.choice.default_note.default_note`). Пусто - подмена молчаливая,
худший вид брака: зритель просит первый сезон, получает соседний и не узнаёт об этом.

С ``--base`` печатается контрфакт против прогона до правки, три меры:

* сколько приговоров сменилось (класс или картина по Enter стали другими);
* сколько подмен УШЛО (был ``ЧУЖОЙ`` - стал ``тот``);
* сколько подмен ПРИШЛО (был ``тот`` - стал ``ЧУЖОЙ``); 🔴 пришло не ноль - не выкатывать.

⚠️ Чего замер НЕ видит. Оба звена читаются по ИМЕНАМ: файлов раздачи щуп не берёт - это
DHT, живая сеть. Случай, где молчат ОБА - и раздача о сезоне, и каталог о части, - этому
щупу неотличим от верного, даже если внутри лежит соседний сезон; сколько таких случаев,
печатается своей строкой (``слепых``), чтобы ноль подмен не читался как ноль беды. Второе:
щуп ходит первый круг плюс сохранённые пулы добора, и за ними боевой поиск ушёл бы дальше -
число подмен поэтому оценка снизу.
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

import anchorprobe
import poolreplay
import runpass
import widenreplay
from probeprofile import add_argument as add_profile_argument
from probeprofile import choose as choose_profile

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.domain.raw_result import RawResult
from torrcast.runtime.wire import wire
from torrcast.usecases.choice.default_note import default_note

#: Классы случая. Один круг одного запроса получает ровно один из них.
SAME = "тот"
OTHER = "ЧУЖОЙ"
NOT_SERIES = "не сериал"
NOTHING = "играть нечем"
UNASKED = "сезона не спрашивали"
CLASSES = (SAME, OTHER, NOT_SERIES, NOTHING, UNASKED)


@dataclass(slots=True)
class Case:
    """Один круг одного запроса: какой сезон спросили и какой уедет зрителю."""

    query: str
    scope: str
    verdict: str = UNASKED
    #: Сезон и серия, названные самим запросом; пусто - запрос их не называл.
    asked: str = ""
    #: Картина по Enter: имя, год, вид.
    played: list[Any] | None = None
    #: Подпись картины: каталог назвал её частью N. ``None`` - номера не носит.
    part: int | None = None
    #: Сезоны, названные вслух ИМЕНЕМ головы очереди; пусто - имя о сезоне молчит.
    named: list[int] = field(default_factory=list)
    #: Имя головы очереди отбора - для глаз: по нему приговор и перепроверяется.
    head_name: str = ""
    #: Сезон не назвали ни раздача, ни каталог: случай щупу невидим.
    blind: bool = False
    #: Честная строка выбора про смену картины; пусто - выбор промолчал.
    note: str = ""


def _told(played: Any) -> list[Any] | None:
    """Личность картины одной строкой: имя, год, вид."""
    return None if played is None else [played.title, played.year, played.kind]


def case_of(query: str, circle: anchorprobe.Circle) -> Case:
    """Разобрать один круг одного запроса в один класс - и назвать обе подписи сезона."""
    out = Case(query=query, scope=circle.scope)
    asked = circle.args.episode
    if asked is None:
        return out
    out.asked = str(asked)
    played = anchorprobe.default_of(circle.plans)
    out.played = _told(played)
    if played is None:
        out.verdict = NOTHING
        return out
    plan = next(one for one in circle.plans if one.picture.key == played.key)
    out.part = played.part
    if plan.want is None:
        out.verdict = NOT_SERIES
        return out
    queue = plan.candidates(circle.args)
    if not queue:
        out.verdict = NOTHING
        return out
    head = plan.ranked[queue[0] - 1]
    out.head_name = head.raw_name
    out.named = list(head.seasons or ((head.season,) if head.season is not None else ()))
    out.blind = not out.named and out.part is None
    out.verdict = SAME if out.named or out.part in (None, asked.season) else OTHER
    if out.verdict == OTHER:
        out.note = default_note(circle.plans, circle.asked)
    return out


def tally(rows: list[Case], scope: str) -> dict[str, int]:
    """Сколько случаев каждого класса на одном круге."""
    mine = [row for row in rows if row.scope == scope]
    return {name: sum(row.verdict == name for row in mine) for name in CLASSES}


def diff(base: list[Case], rows: list[Case]) -> dict[str, int]:
    """Контрфакт против прогона до правки: сменилось, ушло, пришло."""
    was = {(row.query, row.scope): row for row in base}
    pairs = [(was[key], row) for row in rows if (key := (row.query, row.scope)) in was]
    return {
        "сравнимых случаев": len(pairs),
        "сменилось приговоров": sum(
            (old.verdict, old.played) != (new.verdict, new.played) for old, new in pairs
        ),
        "подмен ушло": sum(old.verdict == OTHER and new.verdict == SAME for old, new in pairs),
        "подмен ПРИШЛО": sum(old.verdict == SAME and new.verdict == OTHER for old, new in pairs),
        "молчаливых подмен": sum(new.verdict == OTHER and not new.note for _old, new in pairs),
        "слепых случаев": sum(new.blind for _old, new in pairs),
    }


def report(rows: list[Case], summary: dict[str, int] | None, beyond: int) -> None:
    """Печать замера: тали классов по кругам, разбор подмен и контрфакт."""
    for scope in sorted({row.scope for row in rows}):
        counted = tally(rows, scope)
        told = ", ".join(f"{name} {count}" for name, count in counted.items() if count)
        print(f"\nкруг «{scope}»: запросов {sum(counted.values())}; {told}")
        mine = [row for row in rows if row.scope == scope]
        print(
            f"  слепых (сезон не назвали ни раздача, ни каталог): {sum(row.blind for row in mine)}"
        )
        found = [row for row in mine if row.verdict == OTHER]
        if not found:
            print("  подмен сезона на этом круге нет ни одной")
            continue
        for row in found:
            took = f"{row.played[0]} ({row.played[1]})" if row.played else "-"
            print(
                f"  «{row.query}»: спрошен {row.asked}, идёт «{took}» "
                f"часть {row.part}, имя раздачи о сезоне молчит"
            )
            print(f"      раздача: {row.head_name[:88]}")
            print(f"      строка: {row.note or 'ВЫБОР ПРОМОЛЧАЛ - молчаливая подмена'}")
    if summary is not None:
        print("\nконтрфакт против прогона до правки:")
        for name, count in summary.items():
            print(f"  {name}: {count}")
    print(
        f"\n⚠️ боевой поиск ушёл бы за первый круг у {beyond} запросов - "
        "по ним любое число выше оценка снизу"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pools", type=Path, help="сохранённые выдачи, JSONL")
    parser.add_argument("--facts", type=Path, default=None, help="кэш справки, JSON")
    parser.add_argument("--base", type=Path, default=None, help="прогон до правки, JSONL")
    parser.add_argument("--jsonl", type=Path, default=None, help="куда сложить разбор")
    add_profile_argument(parser)
    args = parser.parse_args(argv)
    wire()
    config, choice = choose_profile(load_config(), args.profile)
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
    ask = widenreplay.facts_passport(args.facts)
    rows: list[Case] = []
    mismatches: list[str] = []
    beyond = 0
    for query in order:
        found, broken, steps = anchorprobe.menus_of(
            query, records[query], pools, config, choice.profile, ask
        )
        rows.extend(case_of(query, one) for one in found)
        mismatches.extend(broken)
        beyond += bool(steps)
    if mismatches:
        for note in mismatches:
            print(f"СЧЁТ НЕ СОШЁЛСЯ: {note}", file=sys.stderr)
        return 1
    base: list[Case] = []
    if args.base is not None:
        base = [
            Case(**json.loads(line))
            for line in args.base.read_text("utf-8").splitlines()
            if line.strip()
        ]
    report(rows, diff(base, rows) if base else None, beyond)
    if args.jsonl is not None:
        with args.jsonl.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
        card = runpass.passport("seasonprobe", [args.pools], sys.argv[1:])
        print(f"\n{runpass.told(card)}\nпаспорт прогона: {runpass.write(card, args.jsonl)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
