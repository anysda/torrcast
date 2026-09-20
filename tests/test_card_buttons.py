"""🔴 В кольце пульта не стоит того, на что фокус не встаёт.

У картины без раздач «Играть» гаснет, и гашёную кнопку браузер не фокусирует вовсе.
Пока она оставалась помеченной ``data-tc-focusable``, пульт считал её остановкой:
стрелка с «Назад» уезжала в неё и не двигалась никуда, а других мест на такой карточке
нет. Снималась пометка присваиванием ``undefined``, а оно ставит атрибут СТРОКОЙ
«undefined» вместо того, чтобы снять его.

Раскладка - в ``tests/web_js/card_buttons.js``, сюда приезжает только кольцо и ходьба.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "card_buttons.js"


@pytest.fixture(scope="module")
def stood() -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node не найден: сторож кольца карточки исполняет card.js", pytrace=False)
    done = subprocess.run(
        [node, str(RUNNER)], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    said: dict[str, Any] = json.loads(done.stdout)
    return said


@pytest.mark.parametrize("screen", ["noReleases", "searching", "found"])
def test_every_stop_of_the_remote_ring_actually_takes_the_focus(
    stood: dict[str, Any], screen: str
) -> None:
    """Кольцо меряется ходьбой по нему, а не наличием пометки: пометка врёт в плюс."""
    shown = stood[screen]
    assert shown["ring"] == shown["reachable"], (
        f"на экране «{screen}» пульт упирается в непроходимое: "
        f"кольцо {shown['ring']}, встаёт фокус только на {shown['reachable']}"
    )


def test_a_dead_play_button_leaves_the_remote_ring_instead_of_blocking_it(
    stood: dict[str, Any],
) -> None:
    shown = stood["noReleases"]
    assert shown["play_disabled"] is True, shown
    assert shown["play_focus_attr"] is None, (
        f"пометка снята присваиванием, а не снята вовсе: {shown['play_focus_attr']!r}"
    )
    assert shown["play_in_ring"] is False, shown


def test_a_picture_with_releases_keeps_its_play_button_in_the_ring(
    stood: dict[str, Any],
) -> None:
    """Отрицательный контроль сторожа: пометка снимается только у гашёной кнопки."""
    assert stood["found"]["play_disabled"] is False, stood["found"]
    assert stood["found"]["play_in_ring"] is True, stood["found"]
    assert stood["searching"]["play_in_ring"] is True, stood["searching"]
