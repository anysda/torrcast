"""Зеркало :mod:`torrcast.domain.facts.search_params`: те же поля, но статьи ищет вики."""

from torrcast.domain.facts.search_params import search_params


def test_the_search_asks_the_same_fields_but_lets_wikipedia_pick_the_articles() -> None:
    """Тот же запрос, но статьи выбирает поиск, а не мы перебором имён."""
    params = search_params("тачки фильм")

    assert params["titles"] == ""
    assert params["generator"] == "search"
    assert params["gsrsearch"] == "тачки фильм"
    assert params["exintro"] == "1", "первую фразу просим точно так же"
