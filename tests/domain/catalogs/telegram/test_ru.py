"""Русский каталог Telegram-показа парен английскому."""

from torrcast.domain.catalogs.telegram.en import en
from torrcast.domain.catalogs.telegram.ru import ru


def test_russian_catalog_has_the_same_keys_and_its_own_line() -> None:
    assert ru().keys() == en().keys()
    assert ru()["telegram.nothing_playing"] == "Показа нет."
