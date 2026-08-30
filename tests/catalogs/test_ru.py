"""Проверки русского каталога Telegram."""

from tgbot.catalogs.en import en as english
from tgbot.catalogs.ru import ru as russian


def test_russian_translates_every_english_key() -> None:
    assert russian().keys() == english().keys()
    assert "MTProto" in russian()["mtproto"]
