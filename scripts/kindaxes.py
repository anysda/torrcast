#!/usr/bin/env python3
"""Щуп TC-854b: разделяют ли оси уровня ФАЙЛОВ линейку серий и части франшизы.

Инструмент разработчика: в устанавливаемый пакет не входит. Сети не нужно -
корпус лежит файлом (`tests/fixtures/file_lists.jsonl`), замер повторяется офлайн.

    python scripts/kindaxes.py            # весь корпус
    python scripts/kindaxes.py --mute     # только там, где боевой разбор сегодня молчит

Предмет. Раздача с голыми номерами файлов (`01.mkv`) на уровне ИМЁН неотличима от
нумерации частей франшизы (`Форсаж [1-4]`). Оси названы ДО замера, `tests/fixtures/kind_axes.md`.

🔴 Мера несимметрична. Пропуск (сериал не узнан) стоит того, что есть сегодня: играет
крупнейший файл. **Подмена** (франшиза названа сериалом) дороже: поедет очередь серий.
Поэтому щуп ищет не «лучший порог», а наибольший улов при ПОДМЕНАХ РОВНО НОЛЬ, и печатает
улов ноль, если такого порога нет. Что прибор умеет отвечать «да» - `tests/test_kindaxes.py`.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import statistics
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, NamedTuple

# Щуп зовёт продукт, поэтому СВОЙ корень идёт впереди путей: с editable-установкой венва
# на соседний клон импорт увёл бы замер в чужое дерево, и число было бы снято не тем кодом.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.domain.map_episodes import map_episodes

ROOT: Final = Path(__file__).resolve().parent.parent
#: Зеркало отбора из :mod:`torrcast.domain.map_episodes`: тот же список расширений,
#: тот же отсев мусора и мелочи. Держится копией, чтобы щуп не лез в приватное.
VIDEO_EXT: Final = (".mkv", ".mp4", ".avi", ".ts", ".m2ts", ".mov", ".webm", ".m4v", ".mpg")
JUNK_RE: Final = re.compile(
    r"\b(?:samples?|trailers?|трейлер\w*|teasers?|creditless|nc-?(?:op|ed)|extras?|"
    r"bonus\w*|бонус\w*|specials?|скриншот\w*|screens?|proof|обложк\w*)\b|"
    r"\bop\s*-\s*ed\b|[/\\](?:openings?|endings?|op|ed)[/\\]",
    re.IGNORECASE,
)
BRACKETS_RE: Final = re.compile(r"[\[(][^\[\]()]*[\])]")
TECH_TOKEN_RE: Final = re.compile(
    r"^(?:\d{3,4}[xх]\d{3,4}|(?:19|20)\d{2}|\d+bit|\d+fps|\d+кбит|\d+kbps|v\d)$", re.I
)
YEAR_RE: Final = re.compile(r"\b(19[3-9]\d|20[0-4]\d)\b")
GIB: Final = 1024.0**3


@dataclass(frozen=True)
class Named:
    """Файл раздачи в форме, которую понимает боевой разбор.

    Не NamedTuple: поле `index` столкнулось бы с `tuple.index`.
    """

    index: int
    name: str
    size: int


def is_mute(row: dict[str, Any]) -> bool:
    """Молчит ли боевой разбор сегодня: явной записи серий в именах нет.

    Класс решения. Порог имеет смысл только здесь: где запись явная, вид уже известен.
    """
    files = [Named(i, str(p), int(z)) for i, (p, z) in enumerate(row["files"])]
    return not map_episodes(files, None, explicit_only=True)


class Axes(NamedTuple):
    """Оси одной раздачи. Сторона - разметка корпуса, а не вывод щупа."""

    side: str
    title: str
    videos: int
    cv: float
    median_gib: float
    padded: float
    dense: float
    years: int
    stem: float


def _videos(files: list[list[Any]]) -> list[tuple[str, int]]:
    """Видеофайлы без мусора и без мелочи - тем же отбором, что и боевой разбор."""
    kept = [
        (str(path), int(size))
        for path, size in files
        if str(path).lower().endswith(VIDEO_EXT) and not JUNK_RE.search(str(path))
    ]
    sizes = [size for _, size in kept if size > 0]
    if len(sizes) < 3:
        return kept
    edge = statistics.median(sizes) * 0.35
    return [(path, size) for path, size in kept if size >= edge or size == 0]


def _bare_number(name: str) -> tuple[int, bool] | None:
    """Голый номер файла и то, записан ли он с ведущим нулём (`01` против `1`)."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
    tokens = [t for t in re.split(r"[\s._\-]+", BRACKETS_RE.sub(" ", base)) if t]
    numbers = [t for t in tokens if t.isdigit() and len(t) <= 3 and not TECH_TOKEN_RE.match(t)]
    if not numbers:
        return None
    last = numbers[-1]
    return int(last), len(last) > 1 and last.startswith("0")


def axes_of(row: dict[str, Any]) -> Axes | None:
    """Оси раздачи; None - видеофайлов меньше двух, паком раздача не является."""
    videos = _videos(row["files"])
    if len(videos) < 2:
        return None
    names = [path.replace("\\", "/").rsplit("/", 1)[-1] for path, _ in videos]
    sizes = [size for _, size in videos]
    mean = statistics.fmean(sizes)
    marks = [_bare_number(name) for name in names]
    numbered = [m for m in marks if m is not None]
    got = sorted(number for number, _ in numbered)
    stem = len(os.path.commonprefix(names))
    return Axes(
        side=row["label"],
        title=row.get("torrent_name") or row.get("title") or "",
        videos=len(videos),
        cv=statistics.stdev(sizes) / mean if len(sizes) > 1 and mean else 0.0,
        median_gib=statistics.median(sizes) / GIB,
        padded=sum(1 for _, zero in numbered if zero) / len(numbered) if numbered else 0.0,
        dense=float(bool(got) and got == list(range(1, len(got) + 1))),
        years=len({m.group(0) for name in names for m in YEAR_RE.finditer(name)}),
        stem=stem / statistics.fmean([len(n) for n in names]),
    )


#: Ось: имя, чем берётся, куда от порога лежит «сериал» (True - не меньше порога).
Pick = Callable[[Axes], float]
AXES: Final[tuple[tuple[str, Pick, bool], ...]] = (
    ("число видеофайлов", lambda r: float(r.videos), True),
    ("разброс веса (СКО/среднее)", lambda r: r.cv, False),
    ("медианный вес файла, ГиБ", lambda r: r.median_gib, False),
    ("доля номеров с ведущим нулём", lambda r: r.padded, True),
    ("плотный ряд 1..N (1 - да)", lambda r: r.dense, True),
    ("разных годов в именах файлов", lambda r: float(r.years), False),
    ("доля общего корня имени", lambda r: r.stem, True),
)


def best_cut(rows: list[Axes], pick: Pick, above: bool, budget: int = 0) -> tuple[float, int, int]:
    """Порог, улов и пропуск при подменах не выше `budget`; улов 0 - порога нет.

    `budget` больше нуля - не предложение, а вторая колонка отчёта: видно цену уступки.
    """
    series = [pick(r) for r in rows if r.side == "S"]
    movies = [pick(r) for r in rows if r.side == "F"]
    best = (float("nan"), 0, len(series))
    for edge in sorted({*series, *movies}):
        if above:
            swap = sum(1 for v in movies if v >= edge)
            caught = sum(1 for v in series if v >= edge)
        else:
            swap = sum(1 for v in movies if v <= edge)
            caught = sum(1 for v in series if v <= edge)
        if swap > budget:
            continue
        if caught > best[1]:
            best = (edge, caught, len(series) - caught)
    return best


def _spread(rows: list[Axes], pick: Pick, name: str) -> None:
    """Разброс одной оси по сторонам: край к краю, чтобы пересечение было видно."""
    print(f"\nось «{name}»")
    for side in ("S", "F"):
        vals = sorted(pick(r) for r in rows if r.side == side)
        if not vals:
            continue
        quart = statistics.quantiles(vals, n=4) if len(vals) > 3 else [float("nan")] * 3
        print(
            f"  {side} (n={len(vals):3d}): мин {vals[0]:7.2f}  Q1 {quart[0]:7.2f}  "
            f"мед {statistics.median(vals):7.2f}  Q3 {quart[2]:7.2f}  макс {vals[-1]:7.2f}"
        )


def report(rows: list[Axes]) -> None:
    """Числа по каждой оси и наибольший безопасный улов; ничего не решает сам."""
    total = sum(r.side == "S" for r in rows)
    print(
        f"корпус: раздач-паков {len(rows)}; сторона S (линейки серий) {total}, "
        f"сторона F (части франшизы) {sum(r.side == 'F' for r in rows)}"
    )
    for name, pick, _above in AXES:
        _spread(rows, pick, name)
    print(f"\n{'ось':>30} {'порог':>9} {'улов при 0 подмен':>18} {'улов при 1 подмене':>19}")
    for name, pick, above in AXES:
        edge, caught, _missed = best_cut(rows, pick, above, budget=0)
        soft_edge, soft, _soft_missed = best_cut(rows, pick, above, budget=1)
        sign = ">=" if above else "<="
        safe = f"{caught}/{total}" if caught else f"НЕТ ПОРОГА (0/{total})"
        print(
            f"  {name:>28} {sign}{edge:8.3f} {safe:>18} {f'{soft}/{total} при {soft_edge:.3f}':>19}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=str(ROOT / "tests/fixtures/file_lists.jsonl.gz"))
    parser.add_argument("--mute", action="store_true", help="только класс решения")
    args = parser.parse_args(argv)
    corpus = Path(args.corpus)
    if not corpus.exists():
        print(f"корпуса нет: {corpus}", file=sys.stderr)
        return 2
    opener = gzip.open if corpus.suffix == ".gz" else open
    with opener(corpus, "rt", encoding="utf-8") as fh:
        packs = [json.loads(x) for x in fh if x.strip()]
    if args.mute:
        packs = [p for p in packs if is_mute(p)]
        print("отобран класс решения: явной записи серий нет")
    found = (axes_of(p) for p in packs)
    rows = [r for r in found if r is not None and r.side in ("S", "F")]
    if not rows:
        print("корпус пуст после отбора паков", file=sys.stderr)
        return 2
    report(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
