#!/usr/bin/env python3
"""Пересобрать ``tests/fixtures/names.txt`` из корпуса реальных имён раздач.

В пакет не входит (§6) — инструмент разработчика. Выборка стратифицированная:
источник × шаблон, по N имён на ячейку, чтобы в фикстурах гарантированно были
все формы записи, а не только самые частые.

    python scripts/make_fixtures.py <корпус>/releases.jsonl
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import re
from pathlib import Path

#: Шаблоны, каждый из которых обязан быть представлен в фикстурах.
PATTERNS: dict[str, str] = {
    "кириллица": r"[а-яА-ЯёЁ]",
    "латиница": r"^[^а-яА-ЯёЁ]+$",
    "2160p": r"\b(2160p|4K|UHD)\b",
    "1080p": r"\b1080p\b",
    "720p": r"\b720[pр]\b",
    "HEVC": r"\b(HEVC|x265|H\.?265)\b",
    "x264": r"\b(x264|AVC|H\.?264)\b",
    "HDR": r"\b(HDR10?\+?|Dolby Vision|DV)\b",
    "remux": r"\b(remux|BDRemux)\b",
    "BDRip": r"\bBD-?Rip\b",
    "WEB-DL": r"\bWEB-?DL",
    "дубляж": r"дубляж|\bДБ\b|\bDub\b",
    "MVO": r"многоголос|\bMVO\b|\bПМ\b",
    "AVO": r"авторск|\bAVO\b|\bАП\b",
    "гоблин": r"гоблин|Пучков|Goblin",
    "субтитры": r"субтитр|\bSub\b|\bСТ\b",
    "X из Y": r"\d+\s*(?:из|of)\s*\d+",
    "sNNeNN": r"\b[Ss]\d{1,2}\s?[Ee]\d{1,3}\b",
    "сезон": r"сезон|\bS\d{2}\b|Season",
    "слэш-формат": r"^[^/]{3,60} / [^/]{3,60}",
    "kinozal-слэши": r"/ (19|20)\d{2} /",
    "скобки-жанры": r"\[(19|20)\d{2},",
    "scene-точки": r"^\S+\.\S+\.\S+\.(19|20)\d{2}\.",
    "аниме-группа": r"^\[[A-Za-z0-9_-]+\]",
    "не-видео": r"\b(FLAC|MP3|PDF|FB2|RePack|lossless)\b",
    "коллекция": r"коллекци|Collection|трилогия|Пенталогия|Квадрология",
    "3D/IMAX": r"\b(3D|3Д|IMAX)\b",
}

HEADER = (
    "# Курируемая выборка реальных имён раздач (этап 1 §7). Отобрана из корпуса\n"
    "# в 21 540 уникальных имён стратифицированно: источник x шаблон, по 6 на ячейку.\n"
    "# Источники: rutor, kinozal, RuTracker, megapeer, TPB, apibay, nyaa, anilibria,\n"
    "# anidub, animelayer, 1337x, YTS. Сам корпус (61 МБ) в репу не кладём.\n"
    "# Строки, начинающиеся с '#', тесты пропускают.\n"
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("corpus", type=Path, help="releases.jsonl из снятого корпуса")
    ap.add_argument("--per-cell", type=int, default=6, help="имён на (источник × шаблон)")
    ap.add_argument("--seed", type=int, default=20260805, help="сид выборки, для повторяемости")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "names.txt",
    )
    args = ap.parse_args()

    seen: set[str] = set()
    rows: list[dict[str, object]] = []
    with args.corpus.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if row["raw_name"] not in seen:
                seen.add(row["raw_name"])
                rows.append(row)

    random.seed(args.seed)
    random.shuffle(rows)
    picked: dict[str, tuple[str, str]] = {}
    per_cell: collections.Counter[tuple[str, str]] = collections.Counter()
    for row in rows:
        name, source = str(row["raw_name"]), str(row.get("source", "?"))
        if len(name) > 220:  # монструозные паки читать в фикстурах невозможно
            continue
        for label, pattern in PATTERNS.items():
            if re.search(pattern, name) and per_cell[(source, label)] < args.per_cell:
                per_cell[(source, label)] += 1
                picked[name] = (source, label)

    names = sorted(picked)
    args.out.write_text(HEADER + "\n".join(names) + "\n", encoding="utf-8")
    print(f"отобрано {len(names)} имён из {len(rows)} → {args.out}")
    for label, pattern in PATTERNS.items():
        print(f"  {label:<16}{sum(1 for n in names if re.search(pattern, n)):>5}")


if __name__ == "__main__":
    main()
