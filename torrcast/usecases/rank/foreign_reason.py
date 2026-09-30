"""Почему раздача пула не про эту картину или не про эту серию; зовут отбор и счёт отсева."""

from __future__ import annotations

from torrcast.domain.episode import Episode
from torrcast.domain.foreign_work import foreign_work
from torrcast.domain.later_form import later_form
from torrcast.domain.other_year import other_year
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.rank.misses_episode import misses_episode


def foreign_reason(release: Release, picture: Picture, want: Episode | None) -> str:
    """Ключ каталога причины, по которой раздача не наша; пусто - наша.

    Отдаётся ключ, а не надпись: очередь отбора зовёт суд на каждую раздачу пула, а
    собирать строку ей незачем. Надпись по ключу (:func:`~torrcast.domain.catalogs.
    phrase.phrase`) собирает только тот, кто объяснение правда выводит.

    Кино другого года (:func:`other_year`), нужной серии нет по имени
    (:func:`misses_episode`), другая работа франшизы (:func:`foreign_work`) или более
    поздняя форма (:func:`later_form`). Порядок один и для очереди отбора
    (:func:`~torrcast.usecases.select.foreign_release.foreign_release`), и для счёта
    отсева (:func:`~torrcast.usecases.rank.drop_reason.drop_reason`): выкинутую раздачу
    объясняют той причиной, на которой её и выкинули, а не первой подошедшей из ворот.
    """
    if other_year(release, picture):
        return "rank.reason_other_year"
    if misses_episode(release, want):
        return "rank.reason_no_episode"
    if want is not None and foreign_work(release, picture):
        return "rank.reason_other_work"
    if want is not None and later_form(release, picture, want):
        return "rank.reason_later_form"
    return ""


__all__ = ["foreign_reason"]
