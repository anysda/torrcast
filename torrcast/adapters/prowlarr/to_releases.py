"""Переводит сырые строки выдачи в релизы: имя разобрано, поля каталога при них."""

from __future__ import annotations

from dataclasses import replace

from torrcast.adapters.prowlarr.magnet_for import magnet_for
from torrcast.domain.nonvideo_release import _is_nonvideo_release
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.raw_result import RawResult
from torrcast.domain.release import Release
from torrcast.domain.sibling_kind import sibling_kind


def to_releases(results: list[RawResult]) -> list[Release]:
    """Разобрать сырую выдачу в релизы, перенеся размер, сиды и magnet.

    Magnet собирается тут (:func:`~torrcast.adapters.prowlarr.magnet_for.magnet_for`), а
    не хранится при строке: у строки есть только хэш и имя, а список публичных
    ретрекеров - хозяйство адаптера, домену он ни о чём не говорит.

    Раздачи без единой видео-приметы, но с приметой звука, картинок, текста или игры
    (:func:`~torrcast.domain.nonvideo_release._is_nonvideo_release`), сюда не доходят
    вовсе: продукту нужно кино, а не саундтрек, артбук, мангу или игру с обложкой.

    Вид раздачи достраивается по всей выдаче разом
    (:func:`~torrcast.domain.sibling_kind.sibling_kind`): имя бывает немо о сериале, а
    соседка по той же выдаче зовёт ту же картину сезоном. Место здесь, потому что здесь
    выдача ЦЕЛА: дальше её разносит по картинам :func:`~torrcast.domain.cluster.cluster`,
    и ключ картины начинается с вида - поднятый позже, он развёл бы одну картину на две.
    """
    return sibling_kind(
        [
            replace(
                parse_release_name(item.title),
                size=item.size,
                seeders=item.seeders,
                magnet=magnet_for(item.info_hash, item.title),
                indexer=item.indexer,
                indexers=item.indexers,
                names=item.names,
                copies=item.copies,
            )
            for item in results
            if not _is_nonvideo_release(item.title)
        ]
    )


__all__ = ["to_releases"]
