#!/usr/bin/env python3
"""Замер порядка «сперва справочник, потом раздачи» по СОХРАНЁННЫМ выдачам.

Инструмент разработчика: в устанавливаемый пакет не входит. Живых служб не нужно ни
одной - ни индексеров, ни справки в сети: справочником тут работает офлайн-карта имён
(та же, что стоит в приборе), и всё, что щуп говорит, он говорит по файлам на диске.

    python scripts/catalogfirst.py pools.jsonl imdb-ru-names.tsv title.ratings.tsv
    python scripts/catalogfirst.py pools.jsonl ru.tsv ratings.tsv --latin latin.tsv

Печатается три числа и списки под ними:

* ПОКРЫТИЕ - у скольких запросов справочник вообще отдаёт список кандидатов. Точным
  именем и по началу имени - это разные числа, и разница между ними важнее каждого из них.
* ЦЕНА - во что обходится чтение справочника с диска. ``cast`` - разовый процесс:
  разобранная карта между запусками не живёт, и справочник, поставленный ПЕРЕД поиском,
  читается на каждый показ и целиком до первой раздачи.
* РАСХОЖДЕНИЯ - где верх списка справочника не совпадает с картиной, которую прибор
  играет сегодня. Числом их не судят, их читают: печатаются поимённо.

Чего замер не видит, названо вслух: сохранённая выдача - это ПЕРВЫЙ круг поиска, и у
запросов с пометкой «дальше» боевой поиск ушёл бы за него; для них всякое число здесь
есть оценка снизу.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Щуп обязан мерить СВОЁ дерево: венв смотрит на клон, а не на этот каталог, и замер,
# снятый одним кодом и подписанный другим, невоспроизводим.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import poolreplay
from probeprofile import choose as choose_profile

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.domain.args import Args
from torrcast.domain.facts.imdb_rows import _ru_rows, _vote_counts
from torrcast.domain.slugify import slugify
from torrcast.runtime.wire import wire
from torrcast.usecases.choice.first_alive import first_alive

if TYPE_CHECKING:
    from torrcast.domain.picture import Picture

#: Типы записей IMDb, которые прибор вообще показывает: короткометражки, эпизоды и
#: видеоигры выгрузка несёт тоже, и в списке кандидатов они были бы шумом.
SHOWN = frozenset({"movie", "tvMovie", "tvSeries", "tvMiniSeries", "video"})
#: Кандидат справочника: имя, год, тип, голоса IMDb.
Candidate = tuple[str, str, str, int]


def _lines(path: Path) -> list[str]:
    with path.open(encoding="utf-8") as handle:
        return handle.readlines()


def _read(path: Path, what: str) -> tuple[dict[str, list[tuple[str, str, str, str, str]]], float]:
    start = time.monotonic()
    names = _ru_rows(_lines(path))
    took = time.monotonic() - start
    print(f"  {what}: {len(names)} имён, разбор {took:.2f} с")
    return names, took


def _look(
    names: dict[str, list[tuple[str, str, str, str, str]]],
    votes: dict[str, int],
    slug: str,
    whole: bool,
) -> list[Candidate]:
    """Кандидаты справочника под запрос; ``whole`` - только точное имя целиком."""
    keys = [slug] if whole else [k for k in names if k == slug or k.startswith(slug + "-")]
    found = [row for key in keys for row in names.get(key, ()) if row[1] in SHOWN]
    found.sort(key=lambda row: -votes.get(row[0], 0))
    return [(row[4], row[3], row[1], votes.get(row[0], 0)) for row in found]


def _named(picture: Picture) -> str:
    return f"{picture.title} ({picture.year or '?'}) [{picture.kind}]"


def _same(candidate: Candidate, picture: Picture) -> bool:
    """Одна ли это картина. Год сильнее имени: у однофамильцев имя одно на всех."""
    if picture.year is not None:
        return candidate[1] == str(picture.year)
    return slugify(candidate[0]) == slugify(picture.title)


def _today(pools: Path) -> list[dict[str, Any]]:
    """Что прибор отвечает сегодня на каждый запрос корпуса."""
    wire()
    config, choice = choose_profile(load_config(), "")
    out: list[dict[str, Any]] = []
    for line in pools.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        query = str(record.get("query", ""))
        item = poolreplay.replay(
            query,
            poolreplay.batches_of(record),
            config,
            choice.profile,
            poolreplay.capped_of(record),
            query,
        )
        plans = item.plans
        out.append(
            {
                "query": query,
                "slug": slugify(Args(query=query.split()).title_query),
                "menu": len(plans),
                "beyond": bool(item.beyond),
                "answer": plans[first_alive(plans) - 1].picture if plans else None,
            }
        )
    return out


def _coverage(rows: list[dict[str, Any]], mode: str) -> None:
    answered = [row for row in rows if row[mode]]
    sizes = sorted(len(row[mode]) for row in answered)
    print(f"\n{mode}: отдал хоть одного кандидата у {len(answered)} запросов из {len(rows)}")
    if not sizes:
        return
    print(
        f"  длина списка: медиана {sizes[len(sizes) // 2]}, макс {sizes[-1]}, "
        f"ровно один кандидат {sum(size == 1 for size in sizes)}, "
        f"десять и больше {sum(size >= 10 for size in sizes)}"
    )
    menus = [row for row in rows if row["menu"] >= 2]
    print(
        f"  меню из 2+ картин сегодня: {len(menus)}; из них справочник свёл бы к одному: "
        f"{sum(len(row[mode]) == 1 for row in menus)}"
    )
    print(
        f"  всего картин в меню сегодня: {sum(row['menu'] for row in rows)}; "
        f"кандидатов у справочника: {sum(len(row[mode]) for row in rows)}"
    )


def _disagreements(rows: list[dict[str, Any]], mode: str) -> None:
    print(f"\n{mode}: верх списка НЕ совпадает с тем, что прибор играет сегодня")
    for row in rows:
        answer, found = row["answer"], row[mode]
        if answer is None or not found or _same(found[0], answer):
            continue
        inside = (
            "нынешняя есть ниже в списке"
            if any(_same(candidate, answer) for candidate in found)
            else "нынешней в списке НЕТ"
        )
        far = ", поиск ушёл бы дальше первого круга" if row["beyond"] else ""
        print(f"  {row['query']:<30} прибор : {_named(answer)}")
        print(
            f"  {'':<30} справка: {found[0][0]} ({found[0][1]}) [{found[0][2]}] "
            f"голосов {found[0][3]}   ({inside}{far})"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pools", type=Path, help="сохранённые выдачи индексеров")
    parser.add_argument("names", type=Path, help="карта русских прокатных имён IMDb")
    parser.add_argument("ratings", type=Path, help="выгрузка оценок IMDb (нужны голоса)")
    parser.add_argument("--latin", type=Path, help="та же карта для оригинальных имён")
    arguments = parser.parse_args(argv)

    print("ЦЕНА чтения справочника с диска (каждый показ - свой процесс cast):")
    names, took = _read(arguments.names, "карта имён")
    if arguments.latin:
        latin, latin_took = _read(arguments.latin, "оригинальные имена")
        for key, extra in latin.items():
            names.setdefault(key, []).extend(extra)
        took += latin_took
    start = time.monotonic()
    votes = _vote_counts(_lines(arguments.ratings))
    took += time.monotonic() - start
    print(f"  голоса IMDb: {len(votes)}, разбор {time.monotonic() - start:.2f} с")
    print(f"  ИТОГО до первой раздачи: {took:.2f} с")

    rows = _today(arguments.pools)
    for row in rows:
        row["точное имя"] = _look(names, votes, row["slug"], whole=True)
        row["начало имени"] = _look(names, votes, row["slug"], whole=False)
    print("\nПОКРЫТИЕ")
    for mode in ("точное имя", "начало имени"):
        _coverage(rows, mode)
    silent = [row["query"] for row in rows if not row["начало имени"]]
    print(f"\nсправочник молчит совсем: {len(silent)} из {len(rows)}")
    print("  " + ", ".join(silent))
    print("\nРАСХОЖДЕНИЯ")
    for mode in ("точное имя", "начало имени"):
        _disagreements(rows, mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
