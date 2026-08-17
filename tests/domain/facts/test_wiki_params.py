"""Проверяет параметры запросов к API Википедии: выборка по именам и поиск."""

from torrcast.domain.facts.settings import _EXLIMIT
from torrcast.domain.facts.wiki_params import _extract_params, _search_params


def test_the_english_link_rides_along_with_the_extracts() -> None:
    """Ссылка на английскую статью не стоит отдельного запроса - едет тем же."""
    params = _extract_params(["Уэнздей"])

    assert "langlinks" in params["prop"]
    assert params["lllang"] == "en"
    assert int(params["lllimit"]) > 1, "потолок общий на все статьи запроса, не на первую"


def test_more_names_than_the_api_takes_are_cut_to_the_limit() -> None:
    """В один запрос влезает ровно :data:`_EXLIMIT` статей - лишние поедут другим пакетом."""
    params = _extract_params([f"Картина {number}" for number in range(_EXLIMIT + 5)])

    assert len(params["titles"].split("|")) == _EXLIMIT


def test_the_search_asks_the_same_fields_but_lets_wikipedia_pick_the_articles() -> None:
    """Тот же запрос, но статьи выбирает поиск, а не мы перебором имён."""
    params = _search_params("тачки фильм")

    assert params["titles"] == ""
    assert params["generator"] == "search"
    assert params["gsrsearch"] == "тачки фильм"
    assert params["exintro"] == "1", "первую фразу просим точно так же"
