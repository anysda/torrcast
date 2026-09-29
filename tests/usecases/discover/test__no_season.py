"""Зеркало отказа «картина есть, нужного сезона нет»: слова консоли и причина страницы."""

from __future__ import annotations

import pytest

from tests.usecases.discover.world import pictures, row
from torrcast.domain.episode import Episode
from torrcast.domain.reason_of import reason_of
from torrcast.usecases.discover._no_season import _no_season


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русская строка отказа консоли рядом с причиной страницы."""


_WEDNESDAY = pictures([row("Уэнсдэй / Wednesday (2022) WEB-DL 1080p", "a")])


def test_the_refusal_names_the_asked_season_in_both_languages_of_its_readers() -> None:
    refusal = _no_season(_WEDNESDAY[0], Episode(9, 1))

    assert "раздач с сезоном 9 нет" in str(refusal)
    reason = reason_of(refusal)
    assert reason.key == "web.search.no_season_releases"
    assert reason.values["season"] == 9


def test_without_an_episode_the_refusal_names_the_first_season() -> None:
    assert reason_of(_no_season(_WEDNESDAY[0], None)).values["season"] == 1
