"""Проверяет обрезку первой фразы статьи под потолок меню."""

from tests.articles import CARS, CLONE_WARS
from torrcast.domain.facts.settings import BLURB_CAP
from torrcast.domain.facts.shorten import shorten


def test_the_description_is_the_whole_first_sentence() -> None:
    """Описание — первая фраза целиком: с жанром и годом, а не огрызок до многоточия."""
    assert shorten(CARS).endswith("Walt Disney Pictures.")
    assert "Режиссёром" not in shorten(CARS), "вторая фраза в меню не нужна"
    assert "..." not in shorten(CARS), "фраза влезла в потолок - резать нечего"


def test_only_a_sentence_past_the_cap_gets_an_ellipsis() -> None:
    """Многоточие остаётся ровно для фраз длиннее всякого разумного потолка."""
    long_one = "«Оппенгеймер» (англ. Oppenheimer) — " + "очень длинное описание, " * 20
    cut = shorten(long_one)
    assert len(cut) <= BLURB_CAP + 3 and cut.endswith("...")
    assert not cut.endswith(",..."), "хвост запятой перед многоточием не нужен"
    assert shorten("«Тачки» — мультфильм. Вторая фраза.", 10) == "«Тачки»..."


def test_the_cap_is_spent_on_the_picture_and_not_on_a_service_pointer() -> None:
    """Под потолок обязана попадать фраза о картине, а не разводка одноимённого.

    Беда TC-908 была не в тесноте потолка: указатель «Не путать с ...» съедал сотню
    символов из отведённых, и поднятие потолка эту строку удлинило бы, а не починило.
    """
    cut = shorten(CLONE_WARS)
    assert not cut.startswith("Не путать")
    assert "анимационный сериал 2008 года" in cut
    assert len(cut) <= BLURB_CAP + 3
