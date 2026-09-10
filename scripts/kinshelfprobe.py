#!/usr/bin/env python3
"""Щуп TC-1114: та же полка родни, но через боевую проводку, а не ручной запрос.

Инструмент разработчика: в устанавливаемый пакет не входит. Ходит в живую сеть
(Википедия и Wikidata) той же проводкой, что и продукт
(:data:`torrcast.runtime.facts_wiring.FACTS`).

    .venv/bin/python scripts/kinshelfprobe.py

Планка: у 8 из 10 известных франшиз полка непуста и без чужих картин. Число тут
обязано сойтись с ручным замером вне репозитория (curl/python по Wikidata SPARQL
напрямую) - расхождение само по себе находка, а не шум.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.runtime.facts_wiring import FactsWiring

#: Десять франшиз приёмки - названа КОНКРЕТНАЯ картина, а не голое имя серии.
#:
#: 🔴 Голое имя франшизы намеренно отвечается статьёй самой франшизы либо никак
#: (:func:`torrcast.domain.facts.read_origin.read_origin`, комментарий про
#: «Гарри Поттер»): у «Миссия невыполнима» и «Джон Уик» так называется и франшиза, и
#: первая картина, и паспорт голого имени поэтому уходит в статью франшизы - это
#: существующее, осознанное поведение паспорта, не моя недоделка. Чтобы спросить
#: КОНКРЕТНУЮ картину этих двух франшиз, взята вторая часть - у неё уже есть номер,
#: и паспорт не путает её со всей серией.
_TITLES: tuple[str, ...] = (
    "Крепкий орешек",
    "Гарри Поттер и философский камень",
    "Пираты Карибского моря: Проклятие Чёрной жемчужины",
    "Матрица",
    "Чужой",
    "Терминатор",
    "Форсаж",
    "Миссия невыполнима 2",
    "Джон Уик 2",
    "Шрек",
)


def main() -> int:
    wiring = FactsWiring()
    hits = 0
    for title in _TITLES:
        origin = wiring.passport.of(title)
        shelf = wiring.franchise.of(title) or []
        names = ", ".join(f"{k.name} ({k.year})" for k in shelf)
        state = "OK" if shelf else "ПУСТО"
        if shelf:
            hits += 1
        print(f"{title!r}: entity={origin.entity or '-'} {state} [{len(shelf)}] {names}")
    print(f"\nПокрытие: {hits} из {len(_TITLES)}")
    return 0 if hits >= 8 else 1


if __name__ == "__main__":
    raise SystemExit(main())
