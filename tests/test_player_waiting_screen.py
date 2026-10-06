"""Между ящиком и первым кадром вкладка показывает фазу подъёма, а не буферизацию.

Ящик показа приходит раньше кадра: упаковщик уже отдал сегмент, а ``<video>`` его ещё не
показал. Раньше вкладка в этот миг меняла экран подготовки на «буферизацию» и больше его
не переписывала, и «жду плеер» (``start.here`` + ``start.packed`` в ``/api/state``) во
вкладке показа был недостижим. Настоящий ``player.js`` в node, сценарии -
``tests/web_js/player_waiting.js``; ``TC.say`` там отдаёт ключ, поэтому страж краснеет и
от подмены самого ключа фразы.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "player_waiting.js"
PREPARING = "web.player.preparing"
WAITING = "web.player.waiting_player"


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


@pytest.mark.parametrize("case", ["here", "early", "died", "quiet"])
def test_the_tab_says_it_waits_for_the_player_until_the_first_frame(
    facts: dict[str, Any], case: str
) -> None:
    seen = facts[case]
    assert seen["packing"]["title"] == PREPARING
    for moment in ("packed", "stalled", "later"):
        assert seen[moment]["title"] == WAITING, f"{case}/{moment}: {seen[moment]}"
        assert not seen[moment]["buffering"], f"{case}/{moment}: буферизация до кадра"


def test_a_tv_start_does_not_say_player(facts: dict[str, Any]) -> None:
    for moment in ("packing", "packed", "stalled", "later"):
        assert facts["tv"][moment]["title"] == PREPARING, facts["tv"][moment]


@pytest.mark.parametrize("case", ["here", "early"])
def test_a_stall_after_the_first_frame_is_buffering(facts: dict[str, Any], case: str) -> None:
    seen = facts[case]
    assert seen["over"] == {"title": None, "buffering": False, "refused": False, "next": False}
    assert seen["afterWaiting"]["buffering"], f"{case}: заминка после кадра не буферизация"
    assert seen["afterWaiting"]["title"] is None


def test_a_start_that_ends_without_a_frame_leaves_the_waiting_screen(
    facts: dict[str, Any],
) -> None:
    assert facts["died"]["over"]["refused"], "показ умер, а вкладка всё ждёт плеер"
    assert facts["died"]["afterWaiting"]["refused"], "заминка мёртвого потока стёрла отказ"
    assert facts["quiet"]["over"]["buffering"], "подъём кончился, а вкладка всё ждёт плеер"
    assert facts["quiet"]["over"]["title"] is None


def test_the_next_episode_plaque_is_not_covered(facts: dict[str, Any]) -> None:
    assert facts["plaque"] == {"title": None, "buffering": False, "refused": False, "next": True}


def test_the_waiting_phase_reaches_the_screen_before_the_next_slow_poll(
    facts: dict[str, Any],
) -> None:
    seen = facts["pace"]
    assert seen["soon"] == WAITING, "фаза «жду плеер» ждала двухсекундного опроса"
    assert seen["beforeBox"] <= 2, f"частый опрос до ящика: {seen['beforeBox']} за 3 с"
    assert seen["afterFrame"] <= 5, f"частый опрос после кадра: {seen['afterFrame']} за 10 с"


def test_the_tab_says_the_torrent_service_was_restarted(facts: dict[str, Any]) -> None:
    assert facts["restart"] == {"during": "web.player.restarted", "after": "web.player.packaging"}
