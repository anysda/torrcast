#!/usr/bin/env python3
"""Контрфакт TC-1033: что маркер серии, взятый не из конца слова, меняет на корпусе-100.

Инструмент разработчика: в устанавливаемый пакет не входит. Сети не нужно - выдачи
индексеров сняты заранее, и замер повторяется по файлу.

    python scripts/spanprobe.py corpus-pools-100.jsonl --out до.json      # на master
    python scripts/spanprobe.py corpus-pools-100.jsonl --out после.json --against до.json

Отбор зовётся продуктовым трактом целиком (:func:`poolreplay.replay`): merge →
to_releases → cluster → pick_franchise → menu_order → plan_for. Ни одна ступень тут не
переписана, поэтому снимок «до» и снимок «после» сравнимы между собой.

Снимок помнит три вещи и сравнение считает ровно по ним:

* вид и имя картины у КАЖДОГО имени - сколько разборов поехало и в какую сторону;
* поимённый список раздач меню - 🔴 сколько раздач ПОТЕРЯНО (планка карточки: ноль);
* верх меню - 🔴 сколько запросов сменило первую строку (планка карточки: ноль).
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from poolreplay import Replay, batches_of, capped_of, replay
from probeprofile import add_argument as add_profile_argument
from probeprofile import choose as choose_profile

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.runtime.wire import wire


def titles_of(record: dict[str, Any]) -> list[str]:
    """Все заголовки строк выдачи записи - до всякого отсева и группировки."""
    rows = record.get("rows")
    if not isinstance(rows, dict):
        return []
    return [
        str(line[0])
        for lines in rows.values()
        for line in lines or ()
        if isinstance(line, list) and line
    ]


def wide_corpus(pools: Path) -> set[str]:
    """Все имена под рукой: выдачи корпуса-100, разметка видов и снятые выдачи TC-854.

    Один корпус-100 узок для правки разбора имён: дефект бьёт по именам, которых в его
    ста запросах может не быть вовсе. Поэтому охват имён считается по всем корпусам
    репы разом, а меню и верх - по корпусу-100, где есть чему ехать.
    """
    root = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
    names: set[str] = set()
    for line in pools.read_text(encoding="utf-8").splitlines():
        if line.strip():
            names.update(titles_of(json.loads(line)))
    names.update(
        line.strip()
        for line in (root / "names.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )
    names.update(
        line.split("\t")[0]
        for line in (root / "default_kind.tsv").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )
    with gzip.open(root / "sibling_results.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            names.add(str(row["raw"]))
            names.update(str(title) for title in row["titles"])
    return {name for name in names if name}


def top_of(item: Replay) -> str:
    """Первая строка меню одной строкой: имя, год и вид - как её печатает щуп."""
    top = item.top
    return "" if top is None else f"{top.title} ({top.year}, {top.kind})"


def shot(item: Replay) -> dict[str, Any]:
    """Что помнить о прогоне одного запроса: верх, размер меню, раздачи поимённо."""
    return {
        "query": item.query,
        "top": top_of(item),
        "menu": len(item.menu),
        "plans": len(item.plans),
        "pictures": len(item.catalog),
        "releases": sorted(
            release.raw_name for picture in item.menu for release in picture.releases
        ),
    }


def take(pools: Path, profile_name: str | None) -> dict[str, Any]:
    """Снять снимок: виды всех имён корпуса и разбор меню по каждому запросу."""
    wire()
    config, choice = choose_profile(load_config(), profile_name)
    kinds = {
        name: f"{(one := parse_release_name(name)).kind}|{one.title}" for name in wide_corpus(pools)
    }
    runs: list[dict[str, Any]] = []
    for line in pools.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        query = str(record.get("query", ""))
        item = replay(query, batches_of(record), config, choice.profile, capped_of(record), query)
        runs.append(shot(item))
    return {"kinds": kinds, "runs": runs}


def kind_diff(before: dict[str, str], after: dict[str, str], show: int) -> list[str]:
    """Сколько разборов поехало: отдельно вид, отдельно имя картины - с образцами."""
    moved = [(name, was, after[name]) for name, was in before.items() if after.get(name) != was]
    kinds = [row for row in moved if row[1].split("|")[0] != row[2].split("|")[0]]
    titles = [row for row in moved if row[1].split("|")[1] != row[2].split("|")[1]]
    ways: dict[str, int] = {}
    for _, was, now in kinds:
        way = f"{was.split('|')[0]}->{now.split('|')[0]}"
        ways[way] = ways.get(way, 0) + 1
    lines = [
        f"имён в корпусе: {len(before)}",
        f"сменило ВИД: {len(kinds)}",
        *(f"  {way}: {count}" for way, count in sorted(ways.items())),
        *(f"  {was}  ->  {now}   {name[:80]}" for name, was, now in kinds[:show]),
        f"сменило ИМЯ картины: {len(titles)}",
        *(f"  {was}  ->  {now}   {name[:80]}" for name, was, now in titles[:show]),
    ]
    return lines


def menu_diff(before: list[dict[str, Any]], after: list[dict[str, Any]], show: int) -> list[str]:
    """Потери раздач, приходы и смены верха меню - поимённо."""
    lost: list[tuple[str, str]] = []
    gained: list[tuple[str, str]] = []
    tops: list[tuple[str, str, str]] = []
    menu_was = menu_now = rows_was = rows_now = 0
    for old, new in zip(before, after, strict=True):
        menu_was, menu_now = menu_was + old["plans"], menu_now + new["plans"]
        rows_was, rows_now = rows_was + len(old["releases"]), rows_now + len(new["releases"])
        old_rows, new_rows = set(old["releases"]), set(new["releases"])
        lost += [(old["query"], name) for name in sorted(old_rows - new_rows)]
        gained += [(old["query"], name) for name in sorted(new_rows - old_rows)]
        if old["top"] != new["top"]:
            tops.append((old["query"], old["top"], new["top"]))
    lines = [
        f"запросов: {len(before)}",
        f"пунктов меню: {menu_was} -> {menu_now}",
        f"раздач в меню: {rows_was} -> {rows_now}",
        f"🔴 раздач ПОТЕРЯНО: {len(lost)}",
        f"раздач пришло: {len(gained)}",
        f"🔴 смен верха меню: {len(tops)}",
    ]
    lines += [f"  ПОТЕРЯНА [{query}] {name[:88]}" for query, name in lost[:show]]
    lines += [f"  пришла   [{query}] {name[:88]}" for query, name in gained[:show]]
    lines += [f"  верх [{query}] {was} -> {now}" for query, was, now in tops[:show]]
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description="контрфакт разбора серий на корпусе выдач")
    ap.add_argument("pools", type=Path, help="pools.jsonl со снятыми выдачами индексеров")
    ap.add_argument("--out", type=Path, required=True, help="куда положить снимок")
    ap.add_argument("--against", type=Path, help="снимок, снятый ДО правки: с чем сравнить")
    ap.add_argument("--show", type=int, default=40, help="сколько строк расписывать")
    add_profile_argument(ap)
    args = ap.parse_args()

    now = take(args.pools, args.profile)
    args.out.write_text(json.dumps(now, ensure_ascii=False), encoding="utf-8")
    print(f"снимок: {args.out} ({len(now['runs'])} запросов, {len(now['kinds'])} имён)")
    if args.against is None:
        return 0
    was = json.loads(args.against.read_text(encoding="utf-8"))
    print("\n".join(kind_diff(was["kinds"], now["kinds"], args.show)))
    print("\n".join(menu_diff(was["runs"], now["runs"], args.show)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
