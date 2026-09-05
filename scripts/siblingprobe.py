#!/usr/bin/env python3
"""Контрфакт TC-854: что правило соседки меняет на корпусе имён.

Инструмент разработчика: в устанавливаемый пакет не входит. Сети не нужно - выдача
источника снята заранее (`scripts/siblingcache.py`), и замер повторяется по файлу.

    python scripts/siblingprobe.py

Считает четыре меры, и главная из них не улов, а подмены:

* сколько видов СМЕНИЛОСЬ;
* сколько подмен УШЛО (было неверно по разметке - стало верно);
* сколько подмен ПРИШЛО (было верно - стало иначе); 🔴 не ноль - не выкатывать;
* у скольких имён пропала разобранная озвучка.

🔴 Граница замера. Запрос к источнику здесь собран из ИМЕНИ САМОЙ раздачи, а человек
ищет картину своими словами. Имя с мусором («Cowboy Bebop + Movie», «One Piece EP1172»)
даёт запрос хуже человеческого, и улов этого щупа - НИЖНЯЯ оценка, а не верхняя.
Подмены такой перекос не занижает: лишних соседок он не добавляет.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.sibling_kind import sibling_kind

ROOT = Path(__file__).resolve().parent.parent
MARKS = ROOT / "tests" / "fixtures" / "default_kind.tsv"
CACHE = ROOT / "tests" / "fixtures" / "sibling_results.jsonl.gz"


def load_marks(path: Path) -> dict[str, str]:
    """Выверенная разметка: имя раздачи → верный вид."""
    marks: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        name, truth, *_ = line.split("\t")
        marks[name] = truth
    return marks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--show", type=int, default=40)
    args = ap.parse_args()

    marks = load_marks(MARKS)
    changed, fixed, broken, lost_voice, empty = [], [], [], [], 0
    total = 0
    with gzip.open(args.cache, "rt", encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            raw, titles = row["raw"], row["titles"]
            total += 1
            if not titles:
                empty += 1
            mine = parse_release_name(raw)
            others = [parse_release_name(t) for t in titles if t != raw]
            after = sibling_kind([mine, *others])[0]
            truth = marks.get(raw, "")
            if mine.kind != after.kind:
                changed.append((raw, mine.kind, after.kind, truth))
                if truth and mine.kind != truth and after.kind == truth:
                    fixed.append(raw)
                if truth and mine.kind == truth and after.kind != truth:
                    broken.append((raw, truth, after.kind))
            if mine.voices and not after.voices:
                lost_voice.append(raw)

    print(f"имён в замере: {total} (пустая выдача источника у {empty})")
    print(f"сменилось видов: {len(changed)}")
    print(f"подмен УШЛО (было неверно - стало верно): {len(fixed)}")
    print(f"подмен ПРИШЛО (было верно - стало иначе): {len(broken)}")
    print(f"пропала озвучка: {len(lost_voice)}")
    if broken:
        print("🔴 ПРИШЕДШИЕ ПОДМЕНЫ:")
        for raw, truth, got in broken[: args.show]:
            print(f"  правда={truth} стало={got}  {raw}")
    print("--- что сменилось:")
    for raw, was, now, truth in changed[: args.show]:
        mark = "ПОЧИНЕНО" if truth and now == truth and was != truth else f"правда={truth or '?'}"
        print(f"  {was}->{now} [{mark}]  {raw[:88]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
