"""Сам круг добора: чем именно спрашиваем каталог второй раз и что из него склеиваем."""

from __future__ import annotations

import torrcast.usecases.discover._search_state as _search_state
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.facts.origin import Origin
from torrcast.domain.goal_spare import CIRCLE_SHARE, GOAL
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.ports.progress.progress import Progress
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.usecases.discover._ask import _ask


def _second_circle(
    client: IndexerClient,
    name: str,
    alt: str,
    index: int | None,
    about: Origin,
    found: list[Picture],
    raw: list[RawResult],
    progress: Progress,
    crowded: bool = False,
) -> list[RawResult]:
    """Второй круг по индексерам и склейка его выдачи с первой; пол бюджета - целая цель.

    Несколько картин под одним коротким именем заполняют широкий латинский поиск свежими
    тёзками. Если независимый паспорт назвал отсутствующий в первом круге год, уточняем
    исходное имя им: это всё тот же один добор, но русская строка сохраняет релизы с
    озвучкой, ради которых человек и назвал картину по-русски.

    ``crowded`` - имя картине отстояла карта IMDb у соседей по слову (:func:`_map_kept`).
    Картина в выдаче одна и год её в круге есть, но слово тесное: «Up» на «Вверх» привозил
    118 картин против 45, гейт отвергал круг, и меню оставалось из 5 раздач вместо 19.

    🔴 TC-386. Круг спрашивается с полом в целую цель: медленный, но живой индексер (на
    живом стенде Knaben отвечал 7.0 с вместо 0.5) в остаток цели не укладывается, и добор
    проходил формально, не привезя ничего, - картина пропадала из каталога так же, как при
    отмене. На здоровом круге пол ничего не стоит: кворум закрывает круг за обычные
    0.5-1.5 с. После захода пол возвращается прежнему.
    """
    exact_year = (
        about.year
        if index is None
        and about.year is not None
        and (crowded or (len(found) > 1 and all(_far(picture, about.year) for picture in found)))
        else None
    )
    asked = f"{name} {exact_year}" if exact_year is not None else alt
    progress.phase(phrase("discover.search_phase", query=asked))
    client.cap_floor = GOAL
    try:
        second = _ask(client, asked)
        # Пока шёл второй круг, один из запросов мог завершиться уже после кворума.
        # Список картин человеку ещё не показан, поэтому готовый хвост можно включить в
        # тот же отбор без ожидания и без подмены уже прочитанного меню. Особенно важен
        # хвост первого круга: картина без латинской подписи по имени добора не найдётся.
        return _search_state._search_catalogue.merge(raw, second, client.late())
    finally:
        client.cap_floor = CIRCLE_SHARE


def _far(picture: Picture, year: int) -> bool:
    return picture.year is None or abs(picture.year - year) > 1
