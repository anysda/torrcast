"""Проверки пояснения сплошного перекода."""

import pytest

from torrcast.domain.recode_note import recode_note


@pytest.fixture(autouse=True)
def _russian_lines(_russian_product: None) -> None:
    """Предмет модуля - русские слова, поэтому язык назван вслух.

    Умолчание продукта английское (:mod:`torrcast.domain.catalogs.tongue`), и без этой
    строки набор мерил бы английскую надпись, а рассказывал бы про русскую.
    """


def test_plain_note() -> None:
    assert recode_note("hevc") == "видео hevc - перекодирую на ходу целиком"
