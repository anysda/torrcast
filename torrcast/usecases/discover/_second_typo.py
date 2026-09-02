"""Круг добора на описку: запрос короче на одно слово, а имя каталога сверяется целиком."""

from __future__ import annotations

import torrcast.usecases.discover._search_state as _search_state
from torrcast.domain.cluster import cluster
from torrcast.domain.facts.origin import Origin
from torrcast.domain.nearly_named import nearly_named
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.domain.slugify import slugify
from torrcast.ports.progress.progress import Progress
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
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
        if found := pick_franchise(near if index is None else f"{near} {index}", seen):
            return pool, seen, found
    return raw, [], []


def _shorter(name: str) -> list[str]:
    """Запрос без одного слова: сперва без самого короткого, потом без самого длинного."""
    words = [word for word in slugify(name).split("-") if word]
    if len(words) < 2:
        return []
    least = min(range(len(words)), key=lambda spot: (len(words[spot]), -spot))
    most = max(range(len(words)), key=lambda spot: (len(words[spot]), -spot))
    return [" ".join(words[:spot] + words[spot + 1 :]) for spot in dict.fromkeys([least, most])]
