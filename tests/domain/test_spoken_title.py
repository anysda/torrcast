"""Зеркало :mod:`torrcast.domain.spoken_title`: имя картины с языковой стороны продукта."""

from torrcast.domain.spoken_title import spoken_title


def test_the_original_name_answers_under_english(_english: None) -> None:
    """Под EN картину зовёт её оригинальное имя - тем же, что строка запуска."""
    assert spoken_title("Ванпанчмен", "One Punch Man") == "One Punch Man"


def test_the_recorded_name_answers_under_russian(_russian_product: None) -> None:
    assert spoken_title("Ванпанчмен", "One Punch Man") == "Ванпанчмен"


def test_a_picture_without_an_original_is_named_as_recorded(_english: None) -> None:
    """Граница способа: оригинала нет (отечественная картина, запись прежней версии) -
    печатается записанное имя как есть, выдуманного у картины нет."""
    assert spoken_title("Луна", "") == "Луна"
