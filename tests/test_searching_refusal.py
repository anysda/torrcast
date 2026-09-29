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
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.nothing_found_error import NothingFoundError
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.search_refusal_error import SearchRefusalError


def _refused(*_args: Any, on_indexer: Any = None) -> Any:
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


@pytest.mark.parametrize("whole", [True, False])
def test_only_a_whole_catalogue_may_say_nothing_to_home_assistant(whole: bool) -> None:
    """Every indexer silent in one window is not «nothing found»: the cut is said with its names."""
    bare = "по запросу «Выживший» ничего не нашлось"
    gone = phrase("hunt.silent", names="Knaben, RuTor")
    cut = phrase("hunt.nothing_cut", query="Выживший", gone=gone)

    def empty(*_args: Any, on_indexer: Any = None) -> Any:
        nothing = NothingFoundError(bare)
        nothing.whole, nothing.silent = whole, ("Knaben", "RuTor")
        raise nothing

    with pytest.raises(RefusedError) as refusal:
        searching(
            Config(prowlarr_apikey="KEY"),
            "Выживший",
            empty,
            lambda _config: Choice(CAUTIOUS, "тест"),
            lambda *_a: None,
            lambda results: results,
        )
    assert refusal.value.word == (bare if whole else cut)


@pytest.mark.parametrize(
    ("fell", "said"),
    [
        ((), phrase("web.search.failed")),
        (
            ("RuTor",),
            phrase(
                "hunt.nothing_cut", query="Выживший", gone=phrase("hunt.refused", names="RuTor")
            ),
        ),
    ],
    ids=["nobody-named", "refused"],
)
def test_a_cut_circle_home_assistant_hears_is_never_a_bare_nothing(
    fell: tuple[str, ...], said: str
) -> None:
    """Without names a cut circle says the search failed; a refusal is named a refusal."""

    def empty(*_args: Any, on_indexer: Any = None) -> Any:
        nothing = NothingFoundError("по запросу «Выживший» ничего не нашлось")
        nothing.whole, nothing.refused = False, fell
        raise nothing

    with pytest.raises(RefusedError) as refusal:
        searching(
            Config(prowlarr_apikey="KEY"),
            "Выживший",
            empty,
            lambda _config: Choice(CAUTIOUS, "тест"),
            lambda *_a: None,
            lambda results: results,
        )
    assert refusal.value.word == said
