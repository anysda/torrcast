#!/usr/bin/env python3
"""Щуп продолжений франшизы: сколько картин своей франшизы не доезжают до меню (офлайн).

Инструмент разработчика: в устанавливаемый пакет не входит. Живых служб не нужно:
пулы - сохранённые выдачи индексеров (формат :mod:`poolreplay`), разбор делает ровно
боевой тракт (:func:`poolreplay.replay`).

    python scripts/contprobe.py pools.jsonl

Раскрытие франшизы в :func:`torrcast.domain.pick_franchise.pick_franchise` держится на ключах вида
``<франшиза>-и-<подзаголовок>``: таких групп-продолжений должно быть не меньше двух.
Щуп считает два класса потерь вокруг этого правила:

* **одиночная и-группа** - продолжение в форме союза ровно одно, и порог «не меньше
  двух» оставляет его за бортом меню. Счёт случаев, где такая картина живая и в меню
  не попала.
* **другие формы ключа** - продолжения, чей ключ отличается иначе (тире, номер версии,
  слово без двоеточия): ``евангелион-1-11``, ``стальной-алхимик-завоеватель-шамбалы``.
  Правило их не раскрывает вовсе, и щуп считает, у скольких запросов такие картины
  мимо меню.

Ключ, который нашёл боевой разбор, щуп не угадывает: он подсматривает вызов
:func:`torrcast.domain.both_languages._both_languages` внутри
:func:`~torrcast.domain.pick_franchise.pick_franchise` (тот же приём, что
:func:`poolreplay.watching_glue`), так что счёт идёт ровно по тому ключу и ровно по тем
группам, с которыми работал продукт.

⚠️ Подмена ставится в модуле, который имя ЧИТАЕТ. Раньше щуп подменял его в плоском
фасаде разбора, а :func:`~torrcast.domain.pick_franchise.pick_franchise` берёт имя из
своих глобалей - шпион не срабатывал НИ РАЗУ, и каждый запрос уходил в счёт «ключа
не нашлось».

Оба класса соседствуют с однофамильцами (``arcane-sorcerer`` рядом с ``arcane``), и щуп
нарочно не отличает своих от чужих: он считает сырой класс, а читать список случаев -
работа глаз.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import poolreplay
from probeprofile import add_argument as add_profile_argument
from probeprofile import choose as choose_profile

from torrcast.adapters.filesystem.state import load_config
from torrcast.cli import Args
from torrcast.domain import pick_franchise as pick_franchise_home
from torrcast.domain.both_languages import _both_languages
from torrcast.domain.picture import Picture
from torrcast.domain.split_franchise_index import split_franchise_index

Groups = dict[str, list[Picture]]

#: Вызовы ``_both_languages`` внутри ``pick_franchise`` за один прогон запроса:
#: (найденный ключ франшизы, группы каталога).
calls: list[tuple[str, Groups]] = []


def _spy(groups: Groups, aliases: dict[str, str], key: str) -> list[Picture]:
    calls.append((key, groups))
    return _both_languages(groups, aliases, key)


patch.object(pick_franchise_home, "_both_languages", _spy).start()


def continuations(key: str, groups: Groups) -> tuple[Groups, Groups]:
    """Живые продолжения ключа: и-формы отдельно, все прочие формы отдельно."""
    and_form: Groups = {}
    other_form: Groups = {}
    for grouped_key, grouped_items in groups.items():
        live = [p for p in grouped_items if p.kind != "other"]
        if not live:
            continue
        if grouped_key.startswith(f"{key}-и-"):
            and_form[grouped_key] = live
        elif grouped_key != key and grouped_key.startswith(f"{key}-"):
            other_form[grouped_key] = live
    return and_form, other_form


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("pools", type=Path, help="pools.jsonl со снятыми выдачами индексеров")
    add_profile_argument(ap)
    args = ap.parse_args(argv)

    config, choice = choose_profile(load_config(), args.profile)
    no_key = with_index = and_two = and_one_lost = and_one_kept = other_lost = 0
    total = 0
    for line in args.pools.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        total += 1
        record = json.loads(line)
        query = str(record.get("query", ""))
        calls.clear()
        item = poolreplay.replay(query, poolreplay.batches_of(record), config, choice.profile)
        _name, index = split_franchise_index(Args(query=query.split()).title_query)
        if not calls:
            no_key += 1
            continue
        if index is not None:
            with_index += 1
            continue
        key, groups = calls[0]
        and_form, other_form = continuations(key, groups)
        menu_keys = {p.key for p in item.menu}
        found: list[str] = []
        if len(and_form) >= 2:
            and_two += 1
        elif len(and_form) == 1:
            group_key, pictures = next(iter(and_form.items()))
            lost = [p for p in pictures if p.key not in menu_keys]
            if lost:
                and_one_lost += 1
                for p in lost:
                    found.append(
                        f"И-ГРУППА ОДНА, МИМО МЕНЮ: «{p.title}» ({p.year}, {p.kind}, "
                        f"раздач {len(p.releases)}) ключ {group_key}"
                    )
            else:
                and_one_kept += 1
        other = [(g, p) for g, pics in other_form.items() for p in pics if p.key not in menu_keys]
        if other:
            other_lost += 1
            for group_key, p in other:
                found.append(
                    f"ДРУГАЯ ФОРМА, МИМО МЕНЮ: «{p.title}» ({p.year}, {p.kind}, "
                    f"раздач {len(p.releases)}) ключ {group_key}"
                )
        if found:
            print(f"=== {query} === ключ «{key}», меню {len(item.menu)}")
            for line_out in found:
                print(f"  {line_out}")

    print(f"\nзапросов всего: {total}")
    print(f"ключ не найден (другой путь pick_franchise): {no_key}")
    print(f"запрошен номер части (ветка раскрытия не работает): {with_index}")
    print(f"и-групп не меньше двух (правило раскрытия отрабатывает): {and_two}")
    print(f"и-группа одна и картина мимо меню: {and_one_lost}")
    print(f"и-группа одна, но картина и так в меню: {and_one_kept}")
    print(f"запросы с продолжениями другой формы мимо меню: {other_lost}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
