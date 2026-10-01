"""Сторож «Отмены» на плашке следующей серии во вкладке (TC-1390) как поведение.

Решение владельца по TC-1394, вариант Б: после «Отмены» серия доигрывает до конца,
затем открывается карточка этого сериала, следующая серия не начинается ни во вкладке,
ни на сервере. Серверная половина - отметка (``tests/test_position.py``,
``tests/adapters/browser/test_browser_receiver.py``), тут - вкладка: настоящие файлы
плеера в node (``tests/web_js/player_cancel.js``), время виртуальное.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "player_cancel.js"
#: Карточка сериала - тот же адрес, что у плитки полки «Продолжить» (`home.js`).
SERIES_CARD = [
    "rick",
    "rick and morty",
    {"title": "Rick and Morty", "shown": "Рик и Морти", "year": 2013, "kind": "series"},
]


@pytest.fixture(scope="module")
def facts() -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node не найден: сторож «Отмены» исполняет player.js в node", pytrace=False)
    done = subprocess.run(
        [node, str(RUNNER)], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    said: dict[str, Any] = json.loads(done.stdout)
    return said


def _scenario(facts: dict[str, Any], name: str) -> dict[str, Any]:
    one: dict[str, Any] = facts[name]
    assert "crashed" not in one, one.get("crashed")
    assert one["errors"] == [], f"сценарий упал посреди прогона: {one['errors']}"
    return one


def _ends_on_the_series_card(said: dict[str, Any]) -> None:
    assert said["card"] == [SERIES_CARD], "на конце не открылась карточка сериала"
    assert said["back"] == 0, "вместо карточки сериала - шаг назад"
    assert said["nextCalls"] == 0
    assert said["key"] == "k1", "вкладка начала следующую серию"


def test_cancel_lets_the_episode_finish_and_opens_the_series_card(facts: dict[str, Any]) -> None:
    said = _scenario(facts, "cancelInTheTab")
    assert said["mounted"] is True
    assert said["saidAtOnce"] is True, "слово «последняя серия» не ушло серверу сразу"
    assert said["plaqueBack"] is False, "плашка вернулась на доигрывающей серии"
    assert said["leftBeforeTheEnd"] == 0, "вкладка ушла, не дав серии доиграть"
    assert said["endedReports"] > 0 and said["endedAllLast"] is True
    _ends_on_the_series_card(said)


def test_cancel_holds_when_the_episode_ended_before_the_tab_said_it(
    facts: dict[str, Any],
) -> None:
    said = _scenario(facts, "cancelAfterTheServerMovedOn")
    assert said["mountedAtClick"] is True
    _ends_on_the_series_card(said)
    assert said["stops"] >= 1, "заведённую сервером следующую серию не сняли"


def test_a_reloaded_tab_keeps_the_cancel(facts: dict[str, Any]) -> None:
    said = _scenario(facts, "reloadAfterCancel")
    assert said["plaque"] is False, "после перезагрузки плашка следующей серии вернулась"
    assert said["reportsLast"] is True, "перезагруженная вкладка потеряла отметку"
    _ends_on_the_series_card(said)


def test_a_second_tab_follows_the_cancel_of_the_first(facts: dict[str, Any]) -> None:
    said = _scenario(facts, "secondTabFollowsTheCancel")
    assert said["sentLast"] is False
    _ends_on_the_series_card(said)


def test_without_cancel_the_tab_leaves_as_before(facts: dict[str, Any]) -> None:
    said = _scenario(facts, "noCancelLeavesAsBefore")
    assert said["sentLast"] is False, "отметка ушла без «Отмены»"
    assert said["card"] == []
    assert said["back"] == 1


def test_the_countdown_follows_the_real_seconds_of_the_video(facts: dict[str, Any]) -> None:
    """Лента вдруг короче (осталось 3 с) - счёт сразу 3, переход приходит с её концом."""
    said = _scenario(facts, "countFollowsTheRealRemainder")
    assert said["seen"] == ["10", "9", "3", "2", "1", None]
