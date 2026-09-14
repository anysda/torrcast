"""Отстояла ли карта IMDb короткое имя у соседей по слову, которым его отдал бы счёт выдачи."""

from __future__ import annotations

from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture
from torrcast.usecases.discover.franchise_pick import franchise_pick


def _map_kept(name: str, pictures: list[Picture]) -> bool:
    """Картины имени по карте другие, чем по одному счёту раздач: имя тесно соседям по слову.

    Так узнаётся ровно тот случай, где карта поменяла ответ (:func:`_richer_namesake`): у
    «Вверх» (Up, 2009) в выдаче семь раздач против «Руки вверх» и ещё двух десятков имён
    со словом. Латинский оригинал такого слова так же тесен, и добору нужен год.
    """
    by_map = {picture.key for picture in franchise_pick(name, pictures)}
    return bool(by_map) and by_map != {picture.key for picture in pick_franchise(name, pictures)}
