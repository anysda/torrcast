#!/usr/bin/env python3
"""Офлайн-переигровка ДОБОРА по второму имени картины на СОХРАНЁННЫХ выдачах.

Инструмент разработчика: в устанавливаемый пакет не входит.

    python scripts/widenreplay.py pools.jsonl --facts facts.json
    python scripts/widenreplay.py pools.jsonl --facts facts.json --jsonl out.jsonl

Живых служб не нужно ни одной: ни Prowlarr, ни справки, ни сети. Второй круг берётся из
того же файла выдач - записью, чей ``query`` равен имени добора; нет такой записи - про
запрос честно печатается «пула добора нет», и в счёт он не идёт.

Повод завести щуп отдельно от :mod:`poolreplay`. Тот проходит ровно ПЕРВЫЙ круг и про
ступени за ним (:data:`poolreplay.BEYOND`) умеет сказать лишь «тут показ ушёл бы дальше»:
за каждой стоит свой запрос к индексерам, которого в одиночном пуле нет. Добор - самая
частая из них, и мерить его было нечем: гейт стоит на счёте привезённых картин, а
сколько их привезено, по одному пулу не видно вовсе.

Печатаются рядом две вещи, и путать их нельзя:

* **что сказал добор** - боевой второй заход
  (:func:`~torrcast.usecases.discover._second_language._second_language`) целиком, вместе
  со строкой вердикта: её словами и назван гейт, который его остановил;
* **что он привёз бы** - те же выдачи, склеенные и разобранные тем же кодом, но без
  приговора: картины каталога, картины меню, раздачи спрошенной франшизы и картина,
  которая пошла бы по Enter (:func:`~torrcast.usecases.choice.first_alive.first_alive`).

Второе - counterfactual, и считается оно ВСЕГДА, даже когда гейт добор отверг: иначе цена
отказа остаётся неизвестной, а без неё про порог гейта сказать нечего.

Паспорта справки читаются из её же кэша на диске (``--facts``), боевым разбором ряда
(:func:`~torrcast.domain.facts.cache_rows._row_origin`). Пустой ряд и отсутствующий файл
значат «справка промолчала» - ровно как при обрыве сети.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import poolreplay
import runpass
from probeprofile import add_argument as add_profile_argument
from probeprofile import choose as choose_profile

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.prowlarr.merge import merge
from torrcast.adapters.prowlarr.to_releases import to_releases
from torrcast.domain.args import Args
from torrcast.domain.cluster import cluster
from torrcast.domain.config import Config
from torrcast.domain.facts.cache_rows import _origin_key, _row_origin
from torrcast.domain.facts.origin import Origin
from torrcast.domain.menu_order import menu_order
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture
from torrcast.domain.profile import Profile
from torrcast.domain.raw_result import RawResult
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.runtime.wire import wire
from torrcast.usecases.choice.first_alive import first_alive
from torrcast.usecases.discover._second_language import _second_language
from torrcast.usecases.discover.season_reread import season_reread
from torrcast.usecases.discover.worth_asking_original import worth_asking_original
from torrcast.usecases.reinforce.plan_for import plan_for

#: Столько секунд щуп обещает добору остатка цели: круг тут ничего не стоит, а отмены по
#: бюджету у добора нет вовсе - мерить надо гейты, а не секундомер.
SPARE = 9.0


class SavedIndexer:
    """Клиент индексеров из сохранённых выдач: сети не касается ни разу."""

    cap_floor = 0.0
    over_goal = False

    def __init__(self, pools: dict[str, list[list[RawResult]]]) -> None:
        self.pools = pools
        self.asked: list[str] = []
        self.missed: list[str] = []

    def search(self, query: str) -> list[RawResult]:
        self.asked.append(query)
        batches = self.pools.get(query.strip().casefold())
        if batches is None:
            self.missed.append(query)
            return []
        return merge(*batches)

    def late(self) -> list[RawResult]:
        return []

    def spare(self) -> float:
        return SPARE


class Quiet:
    """Ход поиска молча в память: вердикт гейта - это его же строка."""

    def __init__(self) -> None:
        self.notes: list[str] = []

    def phase(self, text: str) -> None:
        return None

    def note(self, text: str) -> None:
        self.notes.append(text)

    def stop(self) -> None:
        return None

    def __enter__(self) -> Quiet:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        return None


@dataclass(slots=True)
class Widen:
    """Что добор сказал по одному сохранённому пулу - и что он привёз бы."""

    query: str
    #: Спросил бы боевой поиск второе имя вовсе (:func:`worth_asking_original`).
    worth: bool = False
    #: Чем добор ходил во второй круг; пусто - второго круга не было.
    alt: str = ""
    #: Имена, которых в сохранённых выдачах нет: по ним замер неполон.
    missed: list[str] = field(default_factory=list)
    #: Строки вердикта - ими и назван гейт, остановивший добор.
    notes: list[str] = field(default_factory=list)
    #: Взял ли добор свою выдачу.
    taken: bool = False
    #: Картин каталога до и после; меню - до и после; раздач франшизы - до и после.
    counts: dict[str, int] = field(default_factory=dict)
    #: Картина по Enter до и после добора - той же меркой, что у показа.
    plays: dict[str, list[Any] | None] = field(default_factory=dict)


def facts_passport(path: Path | None) -> Any:
    """Справка из её же кэша на диске: сеть не спрашивается, ряд разбирается боевым кодом."""
    rows: dict[str, Any] = {}
    if path is not None and path.exists():
        rows = json.loads(path.read_text(encoding="utf-8"))

    def ask(title: str, series: bool | None = False, budget: float = 0.0) -> Origin:
        found = _row_origin(rows.get(_origin_key(title, series)))
        return found if found is not None else Origin()

    return ask


def told(picture: Picture | None) -> list[Any] | None:
    """Картина одной строкой: имя, год, раздач - этого хватает, чтобы её опознать."""
    return None if picture is None else [picture.title, picture.year, len(picture.releases)]


def plays(menu: list[Picture], args: Args, config: Config, profile: Profile) -> Picture | None:
    """Картина, которая пойдёт по Enter, - тем же счётом, что у показа."""
    ranked = (plan_for(picture, args, config, profile) for picture in menu_order(menu))
    plans = [plan for plan in ranked if plan.ranked]
    return plans[first_alive(plans) - 1].picture if plans else None


def widen(
    query: str, pools: dict[str, list[list[RawResult]]], config: Config, profile: Profile, ask: Any
) -> Widen:
    """Прогнать один пул через добор и посчитать, чего стоил его приговор."""
    args = Args(query=query.split())
    raw = merge(*pools[query.strip().casefold()])
    first = cluster(to_releases(raw))
    # Ровно порядок круга поиска (:func:`~torrcast.usecases.discover.search_circle.search_circle`):
    # добор спрашивают ИМЕНЕМ запроса, а номер при имени сериала читают сезоном.
    asked = args.title_query
    name, index = split_franchise_index(asked)
    found = pick_franchise(asked, first)
    if (reread := season_reread(args, name, index, found, first)) is not None:
        args, asked = reread, name
    found = menu_order(found)
    out = Widen(query=query, worth=worth_asking_original(found, args, config, profile))
    client, said = SavedIndexer(pools), Quiet()
    merged, _pictures, wider = _second_language(client, asked, args, raw, found, said, passport=ask)
    out.alt = client.asked[0] if client.asked else ""
    out.missed, out.notes = client.missed, said.notes
    out.taken = len(merged) != len(raw) and [p.key for p in wider] != [p.key for p in found]
    # Counterfactual: те же выдачи тем же кодом, но без приговора гейта.
    both = merge(raw, client.search(out.alt)) if out.alt else raw
    catalog = cluster(to_releases(both))
    theirs = menu_order(pick_franchise(asked, catalog))
    out.counts = {
        "строк до": len(raw),
        "строк после": len(both),
        "картин до": len(first),
        "картин после": len(catalog),
        "меню до": len(found),
        "меню после": len(theirs),
        "раздач до": sum(len(p.releases) for p in found),
        "раздач после": sum(len(p.releases) for p in theirs),
    }
    out.plays = {"до": told(plays(found, args, config, profile))}
    out.plays["после"] = told(plays(theirs, args, config, profile))
    return out


def _who(picture: list[Any] | None) -> tuple[Any, Any] | None:
    """Личность картины - имя и год. Счёт раздач в неё не входит: он и меняется добором."""
    return None if picture is None else (picture[0], picture[1])


def report(rows: list[Widen]) -> None:
    """Таблица по доборам: приговор гейта рядом с ценой этого приговора."""
    asked = [row for row in rows if row.worth]
    print(f"запросов {len(rows)}, добор спрашивается в {len(asked)}")
    header = f"{'запрос':<32}{'чужих':>7}{'меню+':>7}{'раздач+':>9}{'доля':>7}  {'взят':<6}играет"
    print(header)
    print("-" * len(header))
    for row in asked:
        if not row.alt or row.missed:
            print(f"{row.query:<32}  пула добора нет: {', '.join(row.missed) or 'имени нет'}")
            continue
        alien = row.counts["картин после"] - row.counts["картин до"]
        gained = row.counts["раздач после"] - row.counts["раздач до"]
        brought = row.counts["строк после"] - row.counts["строк до"]
        share = gained / brought if brought else 0.0
        same = _who(row.plays["до"]) in (None, _who(row.plays["после"]))
        print(
            f"{row.query:<32}{alien:>7}{row.counts['меню после'] - row.counts['меню до']:>7}"
            f"{gained:>9}{share:>7.3f}  {('да' if row.taken else 'нет'):<6}"
            f"{'та же' if same else 'ДРУГАЯ'} {row.plays['после']}"
        )
    for row in asked:
        for note in row.notes:
            print(f"  «{row.query}»: {note}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pools", type=Path, help="сохранённые выдачи, JSONL")
    parser.add_argument("--facts", type=Path, default=None, help="кэш справки, JSON")
    parser.add_argument("--jsonl", type=Path, default=None, help="куда сложить разбор")
    add_profile_argument(parser)
    args = parser.parse_args(argv)
    wire()
    config, _choice = choose_profile(load_config(), args.profile)
    profile = _choice.profile
    pools: dict[str, list[list[RawResult]]] = {}
    order: list[str] = []
    for line in args.pools.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        pools[str(record["query"]).strip().casefold()] = poolreplay.batches_of(record)
        order.append(str(record["query"]))
    ask = facts_passport(args.facts)
    rows = [widen(query, pools, config, profile, ask) for query in order]
    report(rows)
    if args.jsonl is not None:
        with args.jsonl.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
        card = runpass.passport("widenreplay", [args.pools], sys.argv[1:])
        print(f"\n{runpass.told(card)}\nпаспорт прогона: {runpass.write(card, args.jsonl)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
