"""Проверки распознавания строк прокси."""

import pytest

from tgbot.proxy import proxy


@pytest.mark.parametrize(
    "value",
    [
        "http://127.0.0.1:8889",
        "https://user:pass@example.test:443",
        "socks5://127.0.0.1:1080",
        "socks5h://user:pass@example.test:1080",
    ],
)
def test_bot_api_proxy_forms_are_accepted(value: str) -> None:
    assert proxy(value) == (value, None)


def test_mtproto_and_rubbish_are_named() -> None:
    assert proxy("tg://proxy?server=x&port=1&secret=y") == (None, "mtproto")
    assert proxy("banana") == (None, "invalid_proxy")
