"""Зеркало :mod:`hass.hit_ask`: просьба о постере, собранная из записи выдачи."""

from hass.hit_ask import _about, _name
from hass.poster_name import poster_name
from torrcast.domain.facts.ask import Ask
from torrcast.domain.json_value import JsonValue


def test_the_record_of_the_search_becomes_the_ask_of_the_picture() -> None:
    """Оригинальное имя едет вместе с русским: у части находок русской статьи нет вовсе."""
    record: JsonValue = {
        "pick": 1,
        "title": " Паразиты ",
        "year": 2019,
        "kind": "movie",
        "original": "Parasite",
    }
    assert _about(record) == Ask("Паразиты", 2019, "movie", "Parasite")


def test_a_record_without_a_title_is_not_asked_about_at_all() -> None:
    """Без названия картинку не ищут: строка остаётся строкой, а не битой плиткой."""
    assert _about({"pick": 1, "title": "   ", "year": 2019}) is None
    assert _about("не запись") is None


def test_the_kind_comes_down_to_the_two_words_the_card_knows() -> None:
    """Полка общая с карточкой играющего, и третье слово завело бы на ней вторую запись."""
    assert _about({"title": "Уэнздей", "kind": "tv"}) == Ask("Уэнздей", None, "tv")
    assert _about({"title": "Матрица", "kind": "игра"}) == Ask("Матрица", None, "movie")
    assert _about({"title": "Матрица", "year": True}) == Ask("Матрица", None, "movie")


def test_the_name_of_the_picture_is_the_common_name_of_the_shelf() -> None:
    """Имя тут не своё: оно то же самое, каким картину знает карточка играющего."""
    assert _name(Ask("Тачки", 2006, "movie")) == poster_name("Тачки", 2006, "movie")
