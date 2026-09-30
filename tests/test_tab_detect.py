"""Поиск и прогрев процесса страницы судят профилем последней услышанной вкладки."""

from __future__ import annotations

import pytest

from tests.domain.test_tab_key import CHROMIUM_LINUX, IPHONE_SAFARI
from tests.test_hear import _tab
from torrcast.domain.config import Config
from torrcast.domain.profile import BROWSER, CAUTIOUS
from web import hear as said
from web.hear import hear
from web.tab_detect import tab_detect


@pytest.fixture(autouse=True)
def _nobody_heard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(said._HEARD, "tab", "")


def test_the_page_process_judges_by_the_last_tab_it_heard() -> None:
    """Поиск и прогрев судят профилем вкладки, которая говорила последней."""
    config = Config(receiver="browser")
    assert tab_detect(config).profile is CAUTIOUS

    assert hear(_tab(CHROMIUM_LINUX)) == "chromium-linux"
    assert tab_detect(config).profile is BROWSER

    assert hear({"User-Agent": "HomeAssistant/2026.9"}) == ""
    assert tab_detect(config).profile is BROWSER, "молчащий HA не стирает услышанное"

    assert hear(_tab(IPHONE_SAFARI)) == "webkit-ios"
    assert tab_detect(config).profile is CAUTIOUS
