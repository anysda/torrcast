"""Проверки английского каталога Telegram."""

from tgbot.catalogs.en import en


def test_english_is_the_complete_reference_catalog() -> None:
    """Английский - и язык по умолчанию, и запасной каталог: пустых строк в нём нет."""
    catalog = en()
    assert len(catalog) >= 20
    assert all(catalog[key].strip() for key in catalog)
