#!/usr/bin/env python3
"""Замер вида «фильм по умолчанию» на корпусе реальных имён раздач.

Инструмент разработчика: в устанавливаемый пакет не входит.

    python scripts/kindprobe.py
    python scripts/kindprobe.py --jsonl out.jsonl
    python scripts/kindprobe.py --base before.jsonl

Живых служб не нужно ни одной: ни индексеров, ни справки, ни сети.

Предмет замера. Разбор имени раздачи ставит вид «фильм» всякий раз, когда в имени
нет серийных меток (:func:`torrcast.domain.parse_release_name.parse_release_name`): не «увидел
фильм», а «не увидел сериала». Сколько имён корпуса получают вид таким молчанием и у
скольких оно неверно - и есть число этого щупа. Правдой служит выверенная глазами
разметка ``tests/fixtures/default_kind.tsv``: каждый ряд класса обязан быть в ней, и
каждый её ряд обязан быть именем корпуса - иначе счёт молча потерял строку, и об этом
сказано вслух (``MarksMismatchError``), а не сноской.

У неверно названных фильмом сериалов щуп различает форму раздачи: пак (больше одной
серии - у такой картины есть что терять в очереди серий) и одиночная серия.

С ``--base`` печатается контрфакт против прогона до правки, три меры:

* сколько видов сменилось (разбор того же имени дал другой вид);
* сколько подмен УШЛО (было неверно по разметке - стало верно) и сколько ПРИШЛО
  (было верно - стало иначе); 🔴 пришло не ноль - не выкатывать;
* у скольких имён пропала разобранная озвучка (была непустой - стала пустой).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import runpass

from torrcast.domain.parse_release_name import parse_release_name

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "fixtures" / "names.txt"
MARKS = ROOT / "tests" / "fixtures" / "default_kind.tsv"


class MarksMismatchError(Exception):
    """Разметка и класс расходятся: считать по такой разметке нельзя."""


@dataclass(slots=True)
class Row:
    """Одно имя корпуса: что разобрал парсер и что сказала разметка."""

    raw_name: str
    kind: str
    voices: list[str]
    truth: str
    form: str


def load_names(path: Path) -> list[str]:
    """Имена корпуса без комментариев и пустых строк."""
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def load_marks(path: Path) -> dict[str, tuple[str, str]]:
    """Выверенная разметка: имя → (верный вид, форма раздачи)."""
    marks: dict[str, tuple[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        name, truth, *rest = line.split("\t")
        marks[name] = (truth, rest[0] if rest else "")
    return marks


def measure(names: list[str], marks: dict[str, tuple[str, str]]) -> list[Row]:
    """Прогон парсера по корпусу; сверка покрытия - до всякого счёта."""
    unknown = [name for name in marks if name not in set(names)]
    rows = []
    for name in names:
        parsed = parse_release_name(name)
        truth, form = marks.get(name, ("", ""))
        rows.append(
            Row(
                raw_name=name,
                kind=parsed.kind,
                voices=sorted(parsed.voices),
                truth=truth,
                form=form,
            )
        )
    unmarked = [row.raw_name for row in rows if row.kind == "movie" and not row.truth]
    if unknown or unmarked:
        raise MarksMismatchError(
            f"разметки нет у {len(unmarked)} имён класса, "
            f"в разметке {len(unknown)} имён вне корпуса: " + "; ".join((unmarked + unknown)[:5])
        )
    return rows


#: Одна смена вида между прогонами до и после правки:
#: ключи «имя», «было», «стало», «правда».
Change = dict[str, str]

#: Три меры контрфакта и список самих смен; ключи - как в печатаемой строке.
Summary = TypedDict(
    "Summary",
    {
        "сменилось": int,
        "подмен ушло": int,
        "ПОДМЕН ПРИШЛО": int,
        "пропала озвучка": int,
        "смены": list[Change],
    },
)


def diff(base: list[Row], rows: list[Row]) -> Summary:
    """Три меры контрфакта против прогона до правки, по имени раздачи."""
    before = {row.raw_name: row for row in base}
    changed: list[Change] = []
    gone, came, voiceless = 0, 0, 0
    for row in rows:
        old = before.get(row.raw_name)
        if old is None:
            continue
        if old.kind != row.kind:
            changed.append(
                {"имя": row.raw_name, "было": old.kind, "стало": row.kind, "правда": row.truth}
            )
            gone += old.kind != "tv" and row.kind == "tv" and row.truth == "tv"
            came += old.kind == row.truth and row.kind != row.truth
        if old.voices and not row.voices:
            voiceless += 1
    return {
        "сменилось": len(changed),
        "подмен ушло": gone,
        "ПОДМЕН ПРИШЛО": came,
        "пропала озвучка": voiceless,
        "смены": changed,
    }


def report(rows: list[Row], summary: Summary | None) -> None:
    """Печать замера: класс, его цена по разметке и - с базой - три меры."""
    video = [row for row in rows if row.kind != "other"]
    defaulted = [row for row in video if row.kind == "movie"]
    wrong = [row for row in defaulted if row.truth == "tv"]
    junk = [row for row in defaulted if row.truth == "junk"]
    packs = [row for row in wrong if row.form == "пак"]
    print(f"имён в корпусе: {len(rows)} (видео {len(video)}, не-видео {len(rows) - len(video)})")
    print(f"вид «фильм» поставлен молчанием (серийных меток нет): {len(defaulted)}")
    print(f"покрыто разметкой: {sum(bool(row.truth) for row in defaulted)} из {len(defaulted)}")
    print(
        f"неверно названы фильмом: {len(wrong)} сериалов "
        f"(паков {len(packs)}, одиночных серий {len(wrong) - len(packs)})"
        f" и {len(junk)} не-кино"
    )
    for row in wrong:
        print(f"  {row.form or '?'}: {row.raw_name}")
    if junk:
        print("не-кино в классе (другой дефект, не этот замер):")
        for row in junk:
            print(f"  {row.raw_name}")
    if summary is not None:
        print(
            f"\nконтрфакт: сменилось видов {summary['сменилось']}, "
            f"подмен ушло {summary['подмен ушло']}, "
            f"ПОДМЕН ПРИШЛО {summary['ПОДМЕН ПРИШЛО']}, "
            f"пропала озвучка у {summary['пропала озвучка']}"
        )
        for change in summary["смены"]:
            print(
                f"  {change['имя']}: {change['было']} -> {change['стало']} "
                f"(правда: {change['правда'] or 'вне класса'})"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=CORPUS, help="корпус имён, txt")
    parser.add_argument("--marks", type=Path, default=MARKS, help="выверенная разметка, TSV")
    parser.add_argument("--base", type=Path, default=None, help="прогон до правки, JSONL")
    parser.add_argument("--jsonl", type=Path, default=None, help="куда сложить разбор")
    args = parser.parse_args(argv)

    names = load_names(args.corpus)
    marks = load_marks(args.marks)
    try:
        rows = measure(names, marks)
    except MarksMismatchError as beef:
        print(f"СЧЁТ НЕ СОШЁЛСЯ: {beef}", file=sys.stderr)
        return 1
    base: list[Row] = []
    if args.base is not None:
        base = [
            Row(**json.loads(line))
            for line in args.base.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    report(rows, diff(base, rows) if base else None)
    if args.jsonl is not None:
        with args.jsonl.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
        card = runpass.passport("kindprobe", [args.corpus, args.marks], sys.argv[1:])
        print(f"\n{runpass.told(card)}\nпаспорт прогона: {runpass.write(card, args.jsonl)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
