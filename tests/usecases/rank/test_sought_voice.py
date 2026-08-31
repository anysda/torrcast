"""Справка «дорожка на языке зрителя есть»: предмет следует за языком продукта."""

from __future__ import annotations

from tests.usecases.rank.releases import media, track
from torrcast.domain.catalogs.tongue import EN, RU, _choose_tongue
from torrcast.usecases.rank.sought_voice import sought_voice


def test_under_russian_the_sought_voice_is_a_russian_track(_russian_product: None) -> None:
    assert sought_voice(media(tracks=(track(0, "rus", "Дубляж"),)))
    assert not sought_voice(media(tracks=(track(0, "eng", "Original"),)))
    assert not sought_voice(media(tracks=(track(0, None, None),))), "безымянная - не ответ"


def test_under_english_the_sought_voice_is_an_english_track() -> None:
    """🔴 TC-958. Под английской ручкой искомый звук английский - ровно как у яруса
    лестницы. Английская дорожка англоязычной картины - оригинал, и она годна; русский
    дубляж под EN искомым не является."""
    _choose_tongue(EN)
    assert sought_voice(media(tracks=(track(0, "eng", "Original"),)))
    assert not sought_voice(media(tracks=(track(0, "rus", "Дубляж"),)))
    assert not sought_voice(media(tracks=(track(0, None, None),)))


def test_the_language_argument_overrides_the_product_tongue(_russian_product: None) -> None:
    """Явный язык сильнее ручки продукта: гейт зовёт справку с языком намерения."""
    english = media(tracks=(track(0, "eng", "Original"),))
    assert sought_voice(english, EN)
    assert not sought_voice(english, RU)
