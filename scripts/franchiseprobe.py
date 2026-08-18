#!/usr/bin/env python3
"""Щуп TC-449: подтверждает ли справка «часть N франшизы X» вне имени (онлайн-источники).

Инструмент разработчика: в устанавливаемый пакет не входит. Живой Prowlarr не
нужен и не трогается: ходят только Википедия и Wikidata, тем же IPv4-клиентом,
что и боевая справка (:mod:`torrcast.runtime.facts_wiring`).

    python scripts/franchiseprobe.py
    python scripts/franchiseprobe.py pools.jsonl --jsonl out.jsonl

Повод. Строгая мерка :func:`~torrcast.domain.facts.same_name.same_name` отклоняет заголовок вида
«Терминатор 2: Судный день» против запроса «терминатор 2»: заголовок длиннее
спрошенного имени, и по одному имени «подзаголовок спрошенной части» от «другой
картины под знакомым именем» не отличить (TC-338). Вопрос щупа: даёт ли справка
признак ВНЕ имени - Wikidata ``P179`` (часть серии) с квалификатором ``P1545``
(порядковый номер) плюс русская подпись серии, - и насколько он точен.

Два блока, у каждого свой счёт:

* **набор пар** - курируемые случаи: четыре класса из корпуса (подтвердиться
  обязаны), соседние части тех же франшиз, мокбастеры без статьи, голое имя
  франшизы (TC-338) и «Бен 10: Инопланетная сила» (все обязаны молчать);
* **корпус** - запросы с номером части из сохранённых выдач: боевой
  :func:`~torrcast.usecases.passport.Passport.of` против запасного пути (поиск Википедии, который
  отвечает, когда прямого перенаправления «X N» -> статья части нет), и кого из
  той же выдачи подтвердил бы признак.

Wikidata спрашивается пакетно (``VALUES`` на весь прогон, два запроса всего):
поодиночке её штатный ограничитель режет.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import runpass

from torrcast.adapters.wiki.endpoints import (
    _WIKI_HOST,
    _WIKI_PATH,
    _WIKIDATA_HOST,
    _WIKIDATA_PATH,
)
from torrcast.domain.facts.read_origin import read_origin
from torrcast.domain.facts.wiki_params import _extract_params, _search_params
from torrcast.domain.facts.wiki_reply import _pages, _ranked
from torrcast.domain.json_map import json_map
from torrcast.domain.slugify import slugify
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.runtime.facts_wiring import FACTS

#: Курируемый набор: (запрос, заголовок статьи, номер части в запросе, обязан ли
#: признак подтвердить). Позитивы - четыре запроса класса из сохранённого
#: корпуса; контроли - всё, что обязано остаться чужим: соседние части,
#: мокбастеры из того же пула раздач, голое имя франшизы, перезапуск-сериал.
CASES: Final = [
    ("терминатор 2", "Терминатор 2: Судный день", 2, True),
    ("история игрушек 3", "История игрушек: Большой побег", 3, True),
    ("ледниковый период 3", "Ледниковый период 3: Эра динозавров", 3, True),
    ("трансформеры 3", "Трансформеры 3: Тёмная сторона Луны", 3, True),
    ("терминатор 2", "Терминатор 3: Восстание машин", 2, False),
    ("терминатор 2", "Терминатор: Тёмные судьбы", 2, False),
    ("история игрушек 3", "История игрушек 4", 3, False),
    ("история игрушек 3", "История игрушек 5", 3, False),
    ("ледниковый период 3", "Ледниковый период 2: Глобальное потепление", 3, False),
    ("ледниковый период 3", "Ледниковый период 4: Континентальный дрейф", 3, False),
    ("трансформеры 3", "Трансформеры: Месть падших", 3, False),
    ("трансформеры 3", "Трансформеры: Начало", 3, False),
    ("терминатор 2", "Терминатор 2: День страшной забастовки", 2, False),
    ("терминатор 2", "Ниндзя-терминатор", 2, False),
    ("терминатор 2", "Леди-терминатор", 2, False),
    ("терминатор 2", "Женщина-терминатор", 2, False),
    ("матрица", "Матрица: Перезагрузка", None, False),
    ("бен 10", "Бен 10: Инопланетная сила", None, False),
]

#: Пауза между походами в Википедию: щуп гость, а не обходчик.
_PAUSE: Final = 0.5
#: Потолок одного запроса и сколько раз его повторить: Wikidata притормаживает
#: и отвечает 429 - повтор с паузой закрывает это без рук.
_SPARQL_TIMEOUT: Final = 15.0
_SPARQL_TRIES: Final = 5


def sparql(query: str) -> dict[str, Any]:
    """SPARQL к Wikidata с повторами; не ответила - пусто, и это честный «не знаю»."""
    for attempt in range(_SPARQL_TRIES):
        try:
            payload = FACTS.client.get(
                _WIKIDATA_HOST,
                _WIKIDATA_PATH,
                {"query": query},
                {"Accept": "application/sparql-results+json"},
                _SPARQL_TIMEOUT,
            )
            return payload if isinstance(payload, dict) else {}
        except Exception:
            time.sleep(5 * (attempt + 1))
    return {}


def _rows(payload: dict[str, Any]) -> list[Any]:
    """Строки ответа SPARQL; битый ответ - ни одной."""
    return list((payload.get("results", {}) or {}).get("bindings", []) or [])


def _entity(entity: Any) -> str:
    """URI сущности из ответа SPARQL → её Q-идентификатор."""
    return str(entity.get("value", "")).rsplit("/", 1)[-1] if isinstance(entity, dict) else ""


def series_batch(entities: list[str]) -> dict[str, list[tuple[str, str]]]:
    """Q → [(Q-серии, порядковый номер P1545)] одним пакетным запросом по всем сущностям."""
    if not entities:
        return {}
    values = " ".join(f"wd:{entity}" for entity in entities)
    rows = _rows(
        sparql(
            "SELECT ?item ?series ?ordinal WHERE {"
            f" VALUES ?item {{ {values} }}"
            " ?item p:P179 ?stmt . ?stmt ps:P179 ?series ."
            " OPTIONAL { ?stmt pq:P1545 ?ordinal } }"
        )
    )
    out: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        item = _entity(row.get("item"))
        series = _entity(row.get("series"))
        ordinal = str((row.get("ordinal") or {}).get("value", ""))
        if item and series:
            out.setdefault(item, []).append((series, ordinal))
    return out


def labels_batch(entities: list[str]) -> dict[str, str]:
    """Q → русская подпись одним пакетным запросом."""
    if not entities:
        return {}
    values = " ".join(f"wd:{entity}" for entity in entities)
    rows = _rows(
        sparql(
            "SELECT ?item ?label WHERE {"
            f" VALUES ?item {{ {values} }}"
            " ?item rdfs:label ?label . FILTER(LANG(?label) = 'ru') }"
        )
    )
    return {
        item: str((row.get("label") or {}).get("value", ""))
        for row in rows
        if (item := _entity(row.get("item")))
    }


def confirmed_parts(
    candidates: list[tuple[str, str]],
    base: str,
    number: int | None,
    series: dict[str, list[tuple[str, str]]],
    labels: dict[str, str],
) -> list[str]:
    """Кого из кандидатов признак подтверждает частью №`number` серии «`base`».

    Подтверждение - цепочка без единого звена по имени: у сущности кандидата
    есть ``P179`` в серию, квалификатор ``P1545`` этой серии равен спрошенному
    номеру, а русская подпись серии - это имя франшизы из запроса. Номер не
    спрошен (голое имя, «цифра - часть названия») - не подтверждается никто.
    """
    if number is None:
        return []
    out = []
    for heading, entity in candidates:
        for series_q, ordinal in series.get(entity, []):
            label = labels.get(series_q, "").split(" (")[0]
            if ordinal.isdigit() and int(ordinal) == number and slugify(label) == slugify(base):
                out.append(heading)
                break
    return out


def entity_of(heading: str) -> str:
    """Q-идентификатор статьи ru.wikipedia по заголовку; пусто - статьи нет."""
    payload = FACTS.client.get(_WIKI_HOST, _WIKI_PATH, _extract_params([heading]), {}, 8.0)
    _hops, pages = _pages(payload)
    for page in pages.values():
        if page is not None:
            return str(json_map(json_map(page).get("pageprops")).get("wikibase_item") or "")
    return ""


def search_pages(query: str) -> list[Any]:
    """Запасной путь справки: выдача поиска «запрос фильм», как в origin_now."""
    payload = FACTS.client.get(_WIKI_HOST, _WIKI_PATH, _search_params(f"{query} фильм"), {}, 8.0)
    return _ranked(payload)


def numbered_queries(pools: Path | None) -> list[str]:
    """Запросы корпуса с хвостовым номером части (``split_franchise_index`` его режет)."""
    if pools is None:
        return []
    out = []
    for line in pools.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        query = str(json.loads(line).get("query", ""))
        if split_franchise_index(query)[1] is not None:
            out.append(query)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="щуп признака «часть N франшизы X» вне имени")
    ap.add_argument("pools", type=Path, nargs="?", help="pools.jsonl со снятыми выдачами")
    ap.add_argument("--jsonl", type=Path, help="куда положить разбор построчно")
    args = ap.parse_args(argv)
    cmdline = list(argv) if argv is not None else sys.argv[1:]

    # Первый проход - Википедия: сущности курируемого набора и кандидаты корпуса.
    cases = [(q, h, n, want, entity_of(h)) for q, h, n, want in CASES]
    time.sleep(_PAUSE)
    runs: list[dict[str, Any]] = []
    for query in numbered_queries(args.pools):
        base, number = split_franchise_index(query)
        live = FACTS.passport.of(query, series=False, budget=10.0)
        time.sleep(_PAUSE)
        pages = search_pages(query)
        current = read_origin(pages, query, series=False)
        candidates = [
            (
                str(page.get("title") or ""),
                str((page.get("pageprops") or {}).get("wikibase_item") or ""),
            )
            for page in pages
        ]
        runs.append(
            {
                "query": query,
                "base": base,
                "number": number,
                "live": {"name": live.name, "year": live.year, "entity": live.entity},
                "fallback": {"name": current.name, "year": current.year, "entity": current.entity},
                "candidates": candidates,
            }
        )
        time.sleep(_PAUSE)

    # Второй проход - Wikidata, два пакетных запроса на всё.
    all_entities = sorted(
        {entity for *_rest, entity in cases if entity}
        | {entity for run in runs for _h, entity in run["candidates"] if entity}
    )
    series = series_batch(all_entities)
    time.sleep(2)
    labels = labels_batch(sorted({s for rows in series.values() for s, _o in rows}))

    misses = 0
    print("=== набор пар ===")
    for query, heading, number, want, entity in cases:
        base = query.rsplit(" ", 1)[0] if number is not None else query
        got = bool(confirmed_parts([(heading, entity)], base, number, series, labels))
        misses += got != want
        mark = "OK " if got == want else "ПРОМАХ"
        print(f"{mark} «{query}» vs «{heading}»: подтверждено={got} (ждали {want})")
    print(f"пар: {len(CASES)}, промахов признака: {misses}")

    wrong = saved = substituted = gaps = false_confirm = 0
    if runs:
        print("\n=== корпус: запасной путь и признак ===")
        for run in runs:
            live, fallback = run["live"], run["fallback"]
            same = bool(live["entity"]) and fallback["entity"] == live["entity"]
            confirmed = confirmed_parts(
                run["candidates"], run["base"], run["number"], series, labels
            )
            run["confirmed"] = confirmed
            live_heading = next(
                (h for h, e in run["candidates"] if e == live["entity"]), live["name"]
            )
            wrong += not same
            saved += not same and confirmed == [live_heading]
            substituted += not same and bool(confirmed) and confirmed != [live_heading]
            gaps += not same and not confirmed
            # Подтверждение НЕ той статьи, что называет боевая справка, - ложное
            # независимо от того, ошибся ли запасной путь: именно оно стало бы
            # подменой, доверься ему гейт.
            false_confirm += bool(confirmed) and confirmed != [live_heading]
            mark = "OK " if same else "ИНОЕ"
            print(f"{mark} «{run['query']}»: запасной путь {fallback['name']!r} {fallback['year']}")
            print(f"     боевой origin: {live['name']!r} {live['year']}")
            print(f"     признак подтвердил: {confirmed}")
        print(
            f"\nзапросов с номером: {len(runs)}; запасной путь отвечает не про ту часть: "
            f"{wrong}; из них признак исправил бы: {saved}, подменил бы: {substituted}, "
            f"не покрыл: {gaps}; ложных подтверждений признака всего: {false_confirm}"
        )

    if args.jsonl:
        with args.jsonl.open("w", encoding="utf-8") as fh:
            for query, heading, number, want, entity in cases:
                base = query.rsplit(" ", 1)[0] if number is not None else query
                got = bool(confirmed_parts([(heading, entity)], base, number, series, labels))
                fh.write(
                    json.dumps(
                        {
                            "block": "cases",
                            "query": query,
                            "heading": heading,
                            "number": number,
                            "expected": want,
                            "confirmed": got,
                            "entity": entity,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            for run in runs:
                fh.write(json.dumps({"block": "corpus", **run}, ensure_ascii=False) + "\n")
        inputs = [args.pools] if args.pools else []
        card = runpass.passport("franchiseprobe", inputs, cmdline)
        print(f"\n{runpass.told(card)}\nпаспорт прогона: {runpass.write(card, args.jsonl)}")
    return 1 if misses or substituted or false_confirm else 0


if __name__ == "__main__":
    raise SystemExit(main())
