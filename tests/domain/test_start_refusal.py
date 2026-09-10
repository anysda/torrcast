"""Договорные слова отказа: каждое названо классом аварии и одето каталогом страницы."""

from __future__ import annotations

from torrcast.domain.catalogs.web.en import en
from torrcast.domain.catalogs.web.ru import ru
from torrcast.domain.start_refusal import (
    RECEIVER_DID_NOT_ANSWER,
    SOURCE_COULD_NOT_BE_READ,
    SOURCE_DID_NOT_ANSWER,
)

WORDS = (RECEIVER_DID_NOT_ANSWER, SOURCE_DID_NOT_ANSWER, SOURCE_COULD_NOT_BE_READ)


def test_every_word_has_its_line_in_both_page_catalogs() -> None:
    """Страница собирает строку по ключу ``web.player.refused_<слово>`` - ключ обязан быть.

    Именно тут сходится договор: слово пишет умирающий подъём, а строку по нему ищет
    экран. Слова без ключа страница не сочиняет - она покажет короткую строку, и молчание
    каталога стало бы молчанием экрана.
    """
    for word in WORDS:
        assert f"web.player.refused_{word}" in en(), f"каталог en молчит про {word}"
        assert f"web.player.refused_{word}" in ru(), f"зеркало ru молчит про {word}"


def test_the_short_line_without_a_reason_is_there_too() -> None:
    """Причина, которую продукт не различает, остаётся короткой строкой - и она каталожная."""
    assert "web.player.refused" in en()
    assert "web.player.refused" in ru()
