"""Зеркало :mod:`torrcast.domain.facts.extract_params`: запрос за первыми фразами статей."""

from torrcast.domain.facts.extract_params import extract_params
from torrcast.domain.facts.settings import _EXLIMIT


def test_the_english_link_rides_along_with_the_extracts() -> None:
    """Ссылка на английскую статью не стоит отдельного запроса - едет тем же."""
    params = extract_params(["Уэнздей"])

    assert "langlinks" in params["prop"]
    assert params["lllang"] == "en"
    assert int(params["lllimit"]) > 1, "потолок общий на все статьи запроса, не на первую"


def test_more_names_than_the_api_takes_are_cut_to_the_limit() -> None:
    """В один запрос влезает ровно :data:`_EXLIMIT` статей - лишние поедут другим пакетом."""
    params = extract_params([f"Картина {number}" for number in range(_EXLIMIT + 5)])

    assert len(params["titles"].split("|")) == _EXLIMIT
