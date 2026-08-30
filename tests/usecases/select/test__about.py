"""Зеркало строки показа по записи состояния: что человек читает перед стартом."""

from __future__ import annotations

import pytest

from tests.usecases.select.world import entry
from torrcast.usecases.select._about import _about


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - строка показа по записи состояния, читаемая по-русски."""


def test_the_line_names_the_picture_the_episode_the_quality_and_the_voice() -> None:
    """Строка собирается из записи и ровно из неё: ни одного лишнего похода наружу."""
    saved = entry(
        kind="tv",
        season=1,
        episode=2,
        episodes=[[1, 1, 0], [1, 2, 1]],
        quality="1080p",
        voice="Дубляж",
        pos=200.0,
    )

    said = _about(saved)

    assert said == "«Кино» · s1e2 · 1080p · Дубляж · с 0:03:20 · выбрать другое: --menu"


def test_a_nameless_voice_is_named_by_its_number() -> None:
    """Подписи у дорожки нет - человеку называют её номер, а не пустое место."""
    assert _about(entry(pos=0.0, audio=1)) == "«Кино» · дорожка 2 · выбрать другое: --menu"


def test_the_start_of_the_film_is_not_a_place_worth_naming() -> None:
    """Показ с нуля - говорить «с 0:00:00» незачем."""
    assert "с " not in _about(entry(pos=0.0, voice="Дубляж"))


def test_the_line_names_the_handle_that_raises_the_menu() -> None:
    """Играет записанный выбор - и строка сама говорит, чем просят другую картину."""
    assert _about(entry()).endswith("выбрать другое: --menu")


def test_the_line_names_the_studio_that_plays_and_the_one_it_replaced() -> None:
    """Запомненной студии в релизе не нашлось - строка говорит и что играет, и вместо чего."""
    said = _about(entry(pos=0.0, voice="rus", studio="The Kitchen Russia", heard="TVShows"))

    assert said == (
        "«Кино» · rus (TVShows) · озвучка TVShows вместо The Kitchen Russia "
        "· выбрать другое: --menu"
    )
