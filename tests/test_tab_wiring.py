"""Процесс страницы судит поиск, карточку и прогрев профилем той вкладки, что к нему пришла.

Показ получает ключ вкладки доводом (``--tab``), а карточка, отбор дорожек, голова и круг
поиска - только через последний услышанный ключ (:func:`web.hear.hear`). Каждое звено ниже -
провод к нему: оборви любое, и страница судила бы q70d, пока показ судит вкладкой.

Конфиг везде настоящий, приставки нет: живой детектор на нём отвечает осторожным q70d без
сети, так что обрыв провода даёт ровно q70d, а не ошибку.
"""

from __future__ import annotations

from typing import Any

import pytest

import hass.searching
import web.warm_wiring
from tests.domain.test_tab_key import CHROMIUM_LINUX
from torrcast.domain.browser_profile import BROWSER
from torrcast.domain.config import Config
from torrcast.domain.receiver_profile import CAUTIOUS
from web import hear as said
from web.answer_for import answer_for
from web.voice_lookup import _show_profile

#: Вкладка без приставки: профиль ей решает только её ключ.
_ALONE = Config(receiver="browser")
#: То, что кладёт ``web/static/api.js`` у вкладки с MSE и h264 High 5.1.
_ABLE = "tc_tab=mse.hls.avc51"


@pytest.fixture(autouse=True)
def _nobody_heard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(said._HEARD, "tab", "")


@pytest.fixture
def heard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Страница уже услышала замеренную вкладку."""
    monkeypatch.setitem(said._HEARD, "tab", "chromium-linux")


def test_without_a_heard_tab_the_page_judges_by_q70d() -> None:
    """Контроль: без слова вкладки провод отдаёт то же, что детектор, - q70d."""
    assert _show_profile(_ALONE) is CAUTIOUS
    assert hass.searching.DETECT(_ALONE).profile is CAUTIOUS


def test_any_page_request_hears_the_tab_that_sent_it() -> None:
    """После рестарта первым приходит не ``/api/play``, а карточка: её запрос тоже слышится."""
    answer_for("GET", "/no-such-page", None, {"User-Agent": CHROMIUM_LINUX, "Cookie": _ABLE})

    assert _show_profile(_ALONE) is BROWSER


@pytest.mark.usefixtures("heard")
def test_the_card_and_the_track_pick_judge_by_the_heard_tab() -> None:
    """Карточка, судящая q70d, выбрала бы не ту раздачу, что сыграет показ вкладки."""
    assert _show_profile(_ALONE) is BROWSER


@pytest.mark.usefixtures("heard")
def test_the_search_step_judges_by_the_heard_tab() -> None:
    """Шаг поиска моста (``/api/search``) судит тем же профилем, что показ вкладки."""
    assert hass.searching.DETECT(_ALONE).profile is BROWSER


@pytest.mark.usefixtures("heard")
def test_the_warm_circle_judges_by_the_heard_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    """Прогрев карточки ищет тем профилем, каким потом сыграет вкладка."""
    judged: list[Any] = []

    def circle(
        config: Config, args: object, progress: object, profile: Any, **_kw: object
    ) -> list[Any]:
        judged.append(profile)
        return []

    monkeypatch.setattr(web.warm_wiring, "load_config", lambda: _ALONE)
    monkeypatch.setattr(web.warm_wiring, "search_circle", circle)

    web.warm_wiring._search("кино")
    web.warm_wiring._replay("кино", [])

    assert judged == [BROWSER, BROWSER]
