"""Очередь по звуку: раздача, обещающая русскую дорожку именем, спрашивается раньше молчащей."""

from __future__ import annotations

from torrcast.domain.catalogs.tongue import EN, tongue
from torrcast.domain.picture import Picture
from torrcast.domain.rank_settings import ALIVE_SEEDERS
from torrcast.domain.release import Release


def _voice_first(picture: Picture, ranked: list[Release], queue: list[int]) -> list[int]:
    """Живые раздачи с обещанной русской дорожкой вперёд, прочий порядок очереди прежний.

    У «Мы» (2019) №1 без русской дорожки читался 11-15 с и отпадал, а заявившая №7 ждала
    своей очереди: старт 31-40 с. Ступень звука меню (:func:`sound_step`) это место
    уступает качеству, а отбор играет только подтверждённый русский звук (:func:`voice_unproven`),
    так что молчащая раздача раньше заявившей тратит срок зрителя на почти верный отказ.

    Не трогается очередь картины отечественной (своя дорожка не подписывается), английской
    ручки (заявка тут про чужой язык) и мёртвый рой заявившей (:data:`ALIVE_SEEDERS`).
    """
    if picture.native or tongue() == EN:
        return queue
    said = [n for n in queue if _says(ranked[n - 1]) and ranked[n - 1].seeders >= ALIVE_SEEDERS]
    return said + [n for n in queue if n not in said]


def _says(release: Release) -> bool:
    """Имя обещает русскую дорожку: в самом видео или отдельным файлом рядом (TC-305)."""
    return release.dubbed or release.external_dub
