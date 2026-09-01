"""Английские надписи Telegram-показа не содержат русской речи."""

import re

from torrcast.domain.catalogs.telegram.en import en


def test_english_catalog_is_english_and_names_its_cluster() -> None:
    assert all(key.startswith("telegram.") for key in en())
    assert not any(re.search(r"[А-Яа-яЁё]", line) for line in en().values())
    assert en()["telegram.nothing_playing"] == "Nothing is playing."
