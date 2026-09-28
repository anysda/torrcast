"""Страница остаётся английской и при русском языке остального продукта."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.catalogs.tongue import _choose_tongue, tongue


def test_the_page_keeps_its_english_words_when_the_product_is_russian() -> None:
    was = tongue()
    try:
        _choose_tongue("ru")
        assert phrase("web.search.empty") == "Nothing for you"
    finally:
        _choose_tongue(was)
