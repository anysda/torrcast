#!/usr/bin/env python3
"""Прогон парсера по корпусу реальных имён раздач: метрики + топ непарсящихся.

В пакет не входит (§6, бюджет ≤1200 строк) — инструмент разработчика.

    python scripts/corpus_report.py /path/to/corpus/releases.jsonl
    python scripts/corpus_report.py --fails 30 --source rutor …

Корпус (61 МБ) в репе не лежит: снимается отдельно, путь передаётся аргументом.
Курируемая выборка из него — в ``tests/fixtures/names.txt``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.parse import Release, parse_release_name

#: Источники, по которым спрашивают кино и сериалы — на них и целевые ≥95 % (§7).
CINEMA_SOURCES = frozenset({"rutor", "kinozal", "knaben:RuTracker.org", "megapeer"})
_CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)
_YEAR_IN_TEXT = re.compile(r"(?:19|20)\d{2}")
_JUNK_TITLE = re.compile(r"^(?:\d+|[a-zA-Zа-яА-Я]{1,2}|[\W_]+)$")


def title_ok(rel: Release) -> bool:
    """Название считаем извлечённым, если оно не пустое и не вырожденное."""
    return bool(rel.title) and rel.title != "?" and not _JUNK_TITLE.match(rel.title.strip())


def report(rows: list[dict[str, object]], top_fails: int) -> None:
    groups: dict[str, list[tuple[str, Release]]] = {"ВСЕ": [], "кино-имена": [], "хвост": []}
    for row in rows:
        name = str(row["raw_name"])
        source = str(row.get("source", ""))
        rel = parse_release_name(name)
        groups["ВСЕ"].append((source, rel))
        bucket = "кино-имена" if source in CINEMA_SOURCES else "хвост"
        groups[bucket].append((source, rel))

    print("=" * 88)
    print(f"{'группа':<16}{'имён':>8}{'название':>11}{'год':>9}{'назв+год':>11}"
          f"{'качество':>11}{'кодек':>9}{'год есть*':>12}")
    print("-" * 88)
    for label, items in groups.items():
        video = [r for _, r in items if r.kind != "other"]
        n = len(video) or 1
        has_year = [r for r in video if _YEAR_IN_TEXT.search(r.raw_name)]
        m = len(has_year) or 1
        print(f"{label:<16}{len(video):>8}"
              f"{sum(title_ok(r) for r in video) / n:>10.1%}"
              f"{sum(r.year is not None for r in video) / n:>9.1%}"
              f"{sum(title_ok(r) and r.year is not None for r in video) / n:>11.1%}"
              f"{sum(r.quality is not None for r in video) / n:>11.1%}"
              f"{sum(r.codec is not None for r in video) / n:>9.1%}"
              f"{sum(title_ok(r) and r.year is not None for r in has_year) / m:>12.1%}")
    print("=" * 88)
    print("* «год есть» — доля назв+год среди имён, где четырёхзначный год вообще "
          "присутствует в строке:\n  остальное парсеру взять неоткуда (scene-сериалы, "
          "аниме-равки, паки без года).")

    all_rel = [r for _, r in groups["ВСЕ"]]
    print(f"\nотсеяно как не-видео (музыка/книги/игры): "
          f"{sum(r.kind == 'other' for r in all_rel)} из {len(all_rel)}")
    video = [r for r in all_rel if r.kind != "other"]
    print(f"сериалов (kind=tv): {sum(r.kind == 'tv' for r in video)}   "
          f"с озвучкой: {sum(bool(r.voices) for r in video)}   "
          f"с русским названием: {sum(bool(_CYRILLIC.search(r.title)) for r in video)}")

    by_source: Counter[str] = Counter()
    ok_source: Counter[str] = Counter()
    for source, rel in groups["ВСЕ"]:
        if rel.kind == "other":
            continue
        by_source[source] += 1
        if title_ok(rel) and rel.year is not None:
            ok_source[source] += 1
    print("\nназвание+год по источникам:")
    for source, total in by_source.most_common():
        print(f"  {source:<26}{ok_source[source] / total:>7.1%}  ({total})")

    fails = [(s, r) for s, r in groups["ВСЕ"]
             if r.kind != "other" and not (title_ok(r) and r.year is not None)]
    print(f"\nтоп-{top_fails} непарсящихся (нет названия и/или года), всего {len(fails)}:")
    shapes: Counter[str] = Counter()
    examples: dict[str, str] = {}
    for source, rel in fails:
        what = "нет года" if title_ok(rel) else ("нет названия" if rel.year else "нет ничего")
        shape = f"{source} · {what}"
        shapes[shape] += 1
        examples.setdefault(shape, f"{rel.raw_name[:96]}  →  title={rel.title!r}")
    for shape, count in shapes.most_common(top_fails):
        print(f"  {count:>5}  {shape}\n         {examples[shape]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("corpus", type=Path, help="releases.jsonl из снятого корпуса")
    ap.add_argument("--fails", type=int, default=20, help="сколько шаблонов провалов показать")
    ap.add_argument("--dump-fails", type=Path, help="выгрузить все провалы построчно")
    args = ap.parse_args()

    seen: set[str] = set()
    rows: list[dict[str, object]] = []
    with args.corpus.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if row["raw_name"] not in seen:
                seen.add(row["raw_name"])
                rows.append(row)
    print(f"уникальных имён: {len(rows)}\n")
    report(rows, args.fails)

    if args.dump_fails:
        with args.dump_fails.open("w", encoding="utf-8") as fh:
            for row in rows:
                rel = parse_release_name(str(row["raw_name"]))
                if rel.kind != "other" and not (title_ok(rel) and rel.year is not None):
                    fh.write(f"{row.get('source')}\t{rel.title}\t{rel.year}\t{row['raw_name']}\n")


if __name__ == "__main__":
    main()
