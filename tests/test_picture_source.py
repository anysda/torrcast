"""Проверяет сборку источника картинок моста: два источника, их порядок и обе двери."""

from __future__ import annotations

import pytest

from hass.both_posters import BothPosters
from hass.hit_posters import HitPosters
from hass.picture_source import picture_source
from hass.posters import Posters
from torrcast.adapters.wiki.imdb_poster import ImdbPoster
from torrcast.adapters.wiki.wiki_poster import WikiPoster


def test_the_bridge_takes_pictures_from_both_sources_wikipedia_first() -> None:
    """🔴 Порядок тут не вкус: тёзку от тёзки Википедия отличает статьёй, IMDb - годом."""
    source = picture_source()
    assert isinstance(source, BothPosters)
    assert isinstance(source.first, WikiPoster)
    assert isinstance(source.second, ImdbPoster)


def test_the_list_of_hits_takes_its_source_from_this_one_place(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Список находок собирает источник этой сборкой, а не своей."""
    source = picture_source()
    monkeypatch.setattr("hass.hit_posters.picture_source", lambda: source)
    assert HitPosters()._source_of() is source


def test_the_card_of_the_playing_picture_takes_the_very_same_place(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 И карточка играющего тоже: полка у них общая, разойдись - картинки разные."""
    source = picture_source()
    monkeypatch.setattr("hass.posters.picture_source", lambda: source)
    assert Posters()._poster == source.poster
