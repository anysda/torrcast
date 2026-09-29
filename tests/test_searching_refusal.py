"""Отказ шага поиска моста для Home Assistant: фраза продукта, а не код страницы.

Простой ``/api/search`` зовёт только интеграция Home Assistant, и её клиент
(``custom_components/torrcast/serve_client.py``) показывает человеку поле ``error``
тела 409. Код ``search_refused`` с причиной - договор страницы, а не слова для человека.
"""

from __future__ import annotations

from typing import Any

import pytest

from hass.refused_error import RefusedError
from hass.searching import searching
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.search_refusal_error import SearchRefusalError


def _refused(*_args: Any) -> Any:
    raise SearchRefusalError(
        "discover.no_season_releases",
        "web.search.no_season_releases",
        title="Wednesday",
        season=9,
    )


def test_a_named_refusal_reaches_home_assistant_as_the_product_phrase() -> None:
    with pytest.raises(RefusedError) as refusal:
        searching(
            Config(prowlarr_apikey="KEY"),
            "Wednesday s9e1",
            _refused,
            lambda _config: Choice(CAUTIOUS, "тест"),
            lambda *_a: None,
            lambda results: results,
        )
    assert refusal.value.reason is None
    assert refusal.value.body()["error"] == str(refusal.value.__cause__)
    assert "Wednesday" in refusal.value.word, refusal.value.word
