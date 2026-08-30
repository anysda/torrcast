"""Проверки названия видеокодека."""

import pytest

from torrcast.domain.codec_name import codec_name


@pytest.fixture(autouse=True)
def _russian_lines(_russian_product: None) -> None:
    """Предмет модуля - русские слова, поэтому язык назван вслух.

    Умолчание продукта английское (:mod:`torrcast.domain.catalogs.tongue`), и без этой
    строки набор мерил бы английскую надпись, а рассказывал бы про русскую.
    """


def test_depth_is_named() -> None:
    assert codec_name("h264", 10) == "h264 10 бит"
