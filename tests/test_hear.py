"""Слово вкладки о себе по проводу: кука умений доезжает до ``argv`` показа, HA - без неё."""

from __future__ import annotations

import json

import pytest

from hass.play_argv import play_argv
from tests.domain.test_tab_key import CHROMIUM_LINUX
from tests.test_serve import _Bridge, _call, address, bridge  # noqa: F401 - фикстуры
from torrcast.cli.parse_args import parse_args
from web import hear as said
from web.hear import hear

#: То, что кладёт ``web/static/api.js`` у вкладки с MSE и h264 High 5.1.
_ABLE = "tc_tab=mse.hls.avc51"


@pytest.fixture(autouse=True)
def _nobody_heard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(said._HEARD, "tab", "")


def _tab(agent: str, cookie: str = _ABLE) -> dict[str, str]:
    return {"User-Agent": agent, "Cookie": cookie}


def test_play_carries_the_key_of_the_tab_that_asked(address: str, bridge: _Bridge) -> None:  # noqa: F811
    """Кука и ``User-Agent`` запроса - ключ показа; сервер собирает его сам."""
    play = json.dumps({"query": "кино", "here": True}).encode()

    assert _call(f"{address}/api/play", "POST", play, _tab(CHROMIUM_LINUX))[0] == 202
    assert bridge.extras[-1]["tab"] == "chromium-linux"


def test_a_call_without_the_cookie_plays_as_before(address: str, bridge: _Bridge) -> None:  # noqa: F811
    """HA и бот куки не несут: доводы показа те же, что до слова вкладки."""
    play = json.dumps({"query": "кино"}).encode()

    assert _call(f"{address}/api/play", "POST", play, {"User-Agent": CHROMIUM_LINUX})[0] == 202
    assert "tab" not in bridge.extras[-1]


def test_a_mangled_cookie_is_silence_not_a_failure() -> None:
    """Кривая кука - вкладка ничего не сказала, запрос не падает."""
    assert hear({"user-agent": CHROMIUM_LINUX, "cookie": 'tc_tab="\\'}) == ""


def test_the_argv_and_the_cli_agree_on_the_key() -> None:
    """``--tab`` из моста CLI читает тем же словом, а без ключа ``argv`` прежний."""
    argv = play_argv("кино", None, here=True, tab="gecko-linux")

    assert argv == ["кино", "--here", "--tab", "gecko-linux"]
    assert parse_args(argv).tab == "gecko-linux"
    assert play_argv("кино", None, here=True) == ["кино", "--here"]
