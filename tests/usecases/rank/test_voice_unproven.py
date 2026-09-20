"""Гейт дорожки на языке зрителя: у паспорта три ответа, а годен из них только первый."""

from __future__ import annotations

import pytest

from tests.usecases.rank.releases import media, track
from torrcast.domain.catalogs.tongue import EN, _choose_tongue
from torrcast.usecases.rank.voice_unproven import voice_unproven


@pytest.fixture(autouse=True)
def _russian_gate(_russian_product: None) -> None:
    """Предмет четырёх сценариев ниже - русский гейт: он писан до языкового яруса."""


def test_a_named_russian_track_is_proof() -> None:
    assert not voice_unproven(media(tracks=(track(0, "rus", "Дубляж"),)))


def test_a_foreign_passport_sends_the_release_to_the_bench() -> None:
    foreign = media(tracks=(track(0, "jpn", "Original"),))
    assert voice_unproven(foreign)
    assert voice_unproven(foreign, native=True), "чужой язык назван прямо - справка не спасает"


def test_a_lone_unnamed_track_is_proven_regardless_of_origin() -> None:
    """🔴 TC-1288. Единственная безымянная дорожка играет: и у своей картины, и у чужой.

    Решение владельца («1 и 1»): «Универ. Новая общага» и «Ван-Пис» отказывали ровно
    потому, что их единственная дорожка не несла тега языка, а правило TC-741 бракует
    такую раздачу наравне с явно чужой. Здесь оно отменяется - гейт про одну дорожку
    без имени годность больше не спрашивает у ``native`` вовсе.
    """
    unnamed = media(tracks=(track(0, None, None),))
    assert not voice_unproven(unnamed), "иностранная картина - играем, дорожка одна"
    assert not voice_unproven(unnamed, native=True), "«Бригаду» никто не озвучивал"


def test_an_unnamed_track_among_several_is_still_not_a_yes() -> None:
    """🔴 TC-492. Незнание - это не «сойдёт», когда дорожек больше одной.

    Скидка TC-1288 - про ОДНУ дорожку без тега: она и есть весь паспорт файла.
    Когда дорожек несколько, безымянная - лишь одна из версий, и молчание об остальных
    ничего не доказывает; «Лэйн» уехала с нерусской дорожкой ровно по этой причине.
    """
    unnamed_among_others = media(tracks=(track(0, None, None), track(1, "eng", "Original")))
    assert voice_unproven(unnamed_among_others)
    assert not voice_unproven(unnamed_among_others, native=True), "«Бригаду» никто не озвучивал"


def test_a_passport_without_a_single_track_judges_our_haste_not_the_release() -> None:
    """Это не «язык не назван», а «звук не прочитан» - и бракует оно нашу спешку."""
    assert not voice_unproven(media())


def test_under_english_the_proof_is_an_english_track() -> None:
    """🔴 TC-958. Под английской ручкой гейт ищет английский звук, а не русский.

    Английская дорожка англоязычной картины - оригинал, а не дубляж, и гейту она годна;
    русский дубляж под EN годности не даёт - это не язык зрителя.
    """
    _choose_tongue(EN)
    assert not voice_unproven(media(tracks=(track(0, "eng", "Original"),)))
    assert voice_unproven(media(tracks=(track(0, "rus", "Дубляж"),)))


def test_under_english_the_native_discount_does_not_apply() -> None:
    """Скидка ``native`` - про собственную РУССКУЮ дорожку картины: отечественный фильм
    звучит по-русски, и английскому зрителю безымянная дорожка английского не сулит."""
    _choose_tongue(EN)
    unnamed = media(tracks=(track(0, None, None),))
    assert voice_unproven(unnamed, native=True), "«Бригада» под EN английского звука не имеет"
