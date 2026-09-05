#!/usr/bin/env python3
"""Лестница добора вне pytest: сценарий поднимается одной командой и печатает ступени.

Инструмент разработчика: в устанавливаемый пакет не входит.

    python scripts/reinforceprobe.py

Зачем. Ступени добора (второе имя из справки, потолок, сезон, голос, описка) до
поры запускались только изнутри pytest, где внешний мир сценария расставляет
сессионная фикстура: щуп на живом случае падал цепочкой ``NameError: _catalogue
-> _environment -> RuntimeError: no state store assigned`` (TC-1057). Теперь слоты
разводит сама :func:`tests.usecases.discover.world.wire_catalogue`, и лестницу
можно пощупать из чистой оболочки.

Ни одна ступень тут не переписана: щуп зовёт настоящий круг поиска
(:func:`torrcast.usecases.discover.search_circle.search_circle`) и печатает, о чём тот
спросил индексеры, что сказал человеку и что встало в меню. Служб не нужно:
выдача заготовлена зеркалом круга (:mod:`tests.usecases.discover.world`), а разбор,
правила отбора и сама лестница - боевые.

Сценарий - сезонный добор через второе имя: на русское имя источник отвечает
только первым сезоном, справка называет оригинал, и второй заход привозит
спрошенный второй сезон.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.usecases.discover.world import Indexer, Said, row, wire_catalogue
from torrcast.domain.args import Args
from torrcast.domain.catalogs.tongue import RU, _choose_tongue
from torrcast.domain.config import Config
from torrcast.domain.facts.origin import Origin
from torrcast.ports.state_store.slot import store as state_store
from torrcast.usecases.choice.first_alive import first_alive
from torrcast.usecases.discover.search_circle import search_circle

#: Запрос сценария: сериал назван с серией, которой в первой выдаче нет.
QUERY = "харли квинн s2e1"

#: Что отвечает справка: оригинальное имя, за которым уходит второй заход.
PASSPORT = Origin(title="Harley Quinn", year=2019, name="Харли Квинн")

#: Выдача источника: на русское имя - только первый сезон, на оригинал - оба.
ANSWERS = {
    "харли квинн": [
        row("Харли Квинн / Harley Quinn [S01] (2019) WEB-DL 1080p | D", "c", seeders=30),
    ],
    "harley quinn": [
        row("Харли Квинн / Harley Quinn [S01] (2019) WEB-DL 1080p | D", "c", seeders=30),
        row("Харли Квинн / Harley Quinn [S02] (2020) WEB-DL 1080p | D", "d", seeders=90),
    ],
}


def main() -> int:
    # Продукт говорит по-русски - названо, а не досталось умолчанием (тот же
    # держатель языка, что в бою и в наборе: :func:`_choose_tongue`).
    _choose_tongue(RU)
    # Весь внешний мир круга - одной строкой, без ручной сборки: каталог, справка,
    # слоты добора, окружение выбора и хранилище состояния.
    wire_catalogue(passport=PASSPORT)
    client, said = Indexer(answers=ANSWERS), Said()
    plans = search_circle(
        Config(prowlarr_apikey="KEY"),
        Args(query=QUERY.split()),
        said,
        indexer=lambda *_a, **_k: client,
        passport=lambda *_a, **_k: PASSPORT,
    )

    print(f"запрос: {QUERY}")
    print("ступени (что круг спросил у индексеров):")
    for step, asked in enumerate(client.asked, start=1):
        rows = len(ANSWERS.get(asked.casefold(), []))
        print(f"  {step}. «{asked}» - строк выдачи: {rows}")
    print("сказано человеку:")
    for note in said.notes:
        print(f"  {note}")
    print("меню:")
    for number, plan in enumerate(plans, start=1):
        picture = plan.picture
        print(
            f"  [{number}] {picture.title} ({picture.year}, {picture.kind}) - "
            f"в очереди раздач: {len(plan.ranked)}"
        )
    default = plans[first_alive(plans) - 1]
    queue = default.candidates(Args(query=QUERY.split()))
    print(f"по Enter: {default.ranked[queue[0] - 1].raw_name}")
    print(f"память показа: хранилище на месте, записей {len(state_store().load().entries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
