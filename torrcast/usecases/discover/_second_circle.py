"""Сам круг добора: чем именно спрашиваем каталог второй раз и что из него склеиваем."""

from __future__ import annotations

import torrcast.usecases.discover._search_state as _search_state
from torrcast.domain.facts.origin import Origin
from torrcast.domain.goal_spare import CIRCLE_SHARE, GOAL
from torrcast.domain.picture import Picture
from torrcast.ports.progress import Progress
from torrcast.ports.torrent_catalogue import IndexerClient, RawRow
from torrcast.usecases.discover._ask import _ask


def _second_circle(
    client: IndexerClient,
    name: str,
    alt: str,
    index: int | None,
    about: Origin,
    found: list[Picture],
    raw: list[RawRow],
    progress: Progress,
) -> list[RawRow]:
    """Второй круг по индексерам и склейка его выдачи с первой; пол бюджета - целая цель.

    Несколько картин под одним коротким именем заполняют широкий латинский поиск свежими
    тёзками. Если независимый паспорт назвал отсутствующий в первом круге год, уточняем
    исходное имя им: это всё тот же один добор, но русская строка сохраняет релизы с
    озвучкой, ради которых человек и назвал картину по-русски.

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
        and len(found) > 1
        and all(picture.year is None or abs(picture.year - about.year) > 1 for picture in found)
        else None
    )
    asked = f"{name} {exact_year}" if exact_year is not None else alt
    progress.phase(f"поиск «{asked}»")
    client.cap_floor = GOAL
    try:
        second = _ask(client, asked, progress)
        # Пока шёл второй круг, один из запросов мог завершиться уже после кворума.
        # Список картин человеку ещё не показан, поэтому готовый хвост можно включить в
        # тот же отбор без ожидания и без подмены уже прочитанного меню. Особенно важен
        # хвост первого круга: картина без латинской подписи по имени добора не найдётся.
        return _search_state._search_catalogue.merge(raw, second, client.late())
    finally:
        client.cap_floor = CIRCLE_SHARE
