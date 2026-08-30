"""Проверки английского каталога Telegram."""

from tgbot.catalogs.en import en


def test_english_is_the_complete_reference_catalog() -> None:
    assert "401" in en()["http_401"]
    assert len(en()) >= 20
