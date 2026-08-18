"""Зеркально проверяет фасад пакета оживления: прежние имена отвечают из своих файлов."""

from __future__ import annotations

import torrcast.usecases.revive_playback as facade
from torrcast.usecases.revive_playback._hold import _hold
from torrcast.usecases.revive_playback._revival import _Revival


def test_the_old_names_answer_from_the_new_files() -> None:
    """Прежний модуль спрашивают по именам, и фасад отдаёт ровно те же объекты."""
    assert facade._Revival is _Revival
    assert facade._hold is _hold


def test_the_flat_namespace_of_the_monolith_still_finds_its_names() -> None:
    """Плоский namespace прежнего монолита берёт имена отсюда - и все они на месте.

    ⚠️ Прежде тут не спрашивался ``__all__``: совместимый фасад ``torrcast.playback_revival``
    переписывал его своим списком прямо на импорте, и что увидит зеркало, решал порядок
    прогонов. Фасада больше нет, список снова свой - и спрашивается он наравне с именами.
    """
    wanted = [
        "CAUTIOUS",
        "ENDING_RATIO",
        "Feed",
        "REVIVE_TRIES",
        "TAIL_LIMIT",
        "Warmer",
        "_Revival",
        "_configure_revive_playback",
        "_hold",
    ]

    assert [name for name in wanted if not hasattr(facade, name)] == []
    assert [name for name in wanted if name not in facade.__all__] == []
