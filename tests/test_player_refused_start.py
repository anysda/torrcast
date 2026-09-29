"""Отказ подъёма показывает экран отказа, а медленный поиск не уводит вкладку.

``payload()`` отдаёт ``has_next: null`` на ``starting`` и ``idle`` (``hass/payload.py``),
поэтому ожидание следующей серии на подъёме неотличимо от подъёма любой картины. Отказ
первого подъёма (фильма, серии) и отказ следующей серии после стыка обязаны кончаться
экраном отказа со своей строкой, а не главной. Страница на подъёме вида картины не знает
(в снимке ``starting`` полей серии нет), поэтому «фильм» и «серия» тут различаются тем,
что несёт отказ: слово-причину или только строку моста.

Настоящий ``player.js`` в node, сценарии - ``tests/web_js/player_refused.js``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "player_refused.js"


@pytest.fixture(scope="module")
def facts() -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node не найден: сценарии исполняют player.js в node", pytrace=False)
    done = subprocess.run(
        [node, str(RUNNER)], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    said: dict[str, Any] = json.loads(done.stdout)
    return said


@pytest.mark.parametrize(
    ("case", "line"),
    [
        ("film", "web.player.refused: the source did not answer"),
        ("episode", "web.player.refused"),
        ("next", "web.player.refused: the source did not answer"),
    ],
)
def test_a_refused_start_shows_the_refusal_screen(
    facts: dict[str, Any], case: str, line: str
) -> None:
    seen = facts[case]
    assert seen["left"] == 0, f"{case}: отказ увёл вкладку со страницы вместо экрана отказа"
    assert seen["refused"], f"{case}: экрана отказа нет"
    assert seen["line"] == line + "web.player.back"


@pytest.mark.parametrize(
    "case",
    [
        "true/playing",
        "true/paused",
        "true/starting",
        "null/playing",
        "null/paused",
        "null/starting",
    ],
)
def test_a_slow_search_that_finds_the_episode_opens_its_box(
    facts: dict[str, Any], case: str
) -> None:
    seen = facts["slow"][case]
    assert seen["whileSearching"] == 0, "вкладка ушла, пока юнит ещё искал"
    assert seen["afterBox"] == 0, "вкладка ушла, хотя юнит дал новый ящик"
    assert (seen["key"], seen["url"]) == ("k2", "http://stand/b.m3u8")
    assert not seen["pending"]
