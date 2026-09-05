"""Круг добора на описку: запрос короче на одно слово, а имя каталога сверяется целиком."""

from __future__ import annotations

import torrcast.usecases.discover._search_state as _search_state
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.cluster import cluster
from torrcast.domain.facts.origin import Origin
from torrcast.domain.nearly_named import nearly_named
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.domain.slugify import slugify
from torrcast.ports.progress.progress import Progress
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.usecases.discover._ask import _ask
from torrcast.usecases.discover._second_circle import _second_circle


def _second_typo(
    client: IndexerClient,
    name: str,
    index: int | None,
    raw: list[RawResult],
    progress: Progress,
) -> tuple[list[RawResult], list[Picture], list[Picture]]:
    """Пустая выдача при описке в одном слове: спросить короче и опознать имя целиком.

    Описку в одну букву каталог прощает давно (:func:`~torrcast.domain.nearly_named.nearly_named`),
    но до этой ступени не доезжают: слово с опиской стоит в самом запросе, индексер ищет
    строкой и на «байки метра» не отдаёт НИ ОДНОЙ строки, тогда как на «байки» отдаёт сто
    с лишним, и одиннадцать из них - та самая картина. Спрашивать было чем, а мы не
    спрашивали.

    Поэтому запрос укорачивается на одно слово и спрашивается заново. Слов пробуется два:
    сперва роняем самое короткое (в нём меньше всего смысла, а остаток - самый узкий
    запрос из возможных), потом самое длинное (в нём больше всего места для описки).
    Двух хватает, чтобы запрос из двух слов был перебран целиком; на длинном запросе это
    уже догадка, и цена ей - ровно два круга, а не сколько слов, столько и кругов.

    🔴 **Широкий запрос не вправе подменить картину.** Из ста с лишним строк по слову
    «байки» к Мэтру относятся одиннадцать, и взять оттуда вожака широкой выдачи было бы
    хуже честного отказа: :func:`~torrcast.domain.pick_franchise.pick_franchise` на таком
    пуле цепляется за имя, которое всего лишь ВХОДИТ в запрос («Унесенные» на «унесённые
    призракоми»), и человек молча получает не ту картину. Поэтому расширенная выдача сама
    по себе ничего не решает: ворота тут одни - имя каталога, отличающееся от ВСЕГО
    запроса ровно одной буквой и единственное такое. Не нашлось - выдачи как не было, и
    отказ остаётся прежним, слово в слово.

    Заводится это только на пустой выдаче: запрос, нашедшийся с первого круга, ветки не
    видит и не платит за неё ни секунды. Одно слово укорачивать не во что - и там ветка
    молчит тоже («лёд», «дюна»).

    🔴 TC-1004. **Одним коротким словом судьба картины не решается.** Опознав имя, ступень
    спрашивает источник ЕЩЁ РАЗ - тем самым именем, которое человек и набирал бы без промаха
    клавиши, - и склеивает эту выдачу с широкой. Без второго вопроса картина выбиралась на
    пуле по одному слову: на «байки» сериал отдавался с мёртвым роем, а на «байки мэтра» - с
    живым, и одна буква уводила зрителя с сериала на одноимённый фильм. Правило вида
    (:func:`~torrcast.usecases.choice.series_take.series_take`) спрашивается на общем пуле, и
    спросить его есть о чём только когда в пуле лежат обе картины.

    ⚠️ Ступень по-прежнему стоит В ХВОСТЕ круга, ПОСЛЕ справки по оригинальному имени
    (:func:`~torrcast.usecases.discover._second_language._second_language`), и это замер, а не
    вкус: поднятая наверх, она отнимает у справки её случаи и заставляет платить два лишних
    захода к источнику там, где справка чинит запрос сама («мальчик и цапля», «ре зеро»).
    Цена этого - доборы под потолок, сезон и озвучку на путь описки не попадают.

    ⚠️ Пол бюджета круга берётся у самого добора (:func:`_second_circle`, TC-386), своего
    тут не заводится.
    """
    pool = raw
    for shorter in _shorter(name):
        pool = _second_circle(client, name, shorter, None, Origin(), [], pool, progress)
        progress.phase("")
        seen = cluster(_search_state._search_catalogue.to_releases(pool))
        if not (near := nearly_named(name, seen)):
            continue
        # Номер части переспрашивается вместе с исправленным именем: описка правится в
        # имени, а не в номере («байки метра 2» - это по-прежнему просьба про вторую).
        asked = near if index is None else f"{near} {index}"
        if not pick_franchise(asked, seen):
            continue
        # 🔴 TC-1004. Исправленным именем источник спрашивается ещё раз, и выдача его
        # склеивается с широкой. Иначе судьба картины решалась бы по одному короткому слову.
        fixed = near.replace("-", " ")
        progress.phase(phrase("discover.search_phase", query=fixed))
        pool = _search_state._search_catalogue.merge(pool, _ask(client, fixed))
        progress.phase("")
        seen = cluster(_search_state._search_catalogue.to_releases(pool))
        return pool, seen, pick_franchise(asked, seen)
    return raw, [], []


def _shorter(name: str) -> list[str]:
    """Запрос без одного слова: сперва без самого короткого, потом без самого длинного."""
    words = [word for word in slugify(name).split("-") if word]
    if len(words) < 2:
        return []
    least = min(range(len(words)), key=lambda spot: (len(words[spot]), -spot))
    most = max(range(len(words)), key=lambda spot: (len(words[spot]), -spot))
    return [" ".join(words[:spot] + words[spot + 1 :]) for spot in dict.fromkeys([least, most])]
