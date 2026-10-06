"""A seek made outside the tab (card, Home Assistant, bridge) pulls the tab's film back on TV.

The tab hears such a seek only as a report, and a report behind the film read as a stale
tail: the TV went to 745.1 while the film stayed on 1062. The bridge numbers each of its
seeks in the snapshot (``seek``), and a new number arms the same pull as a press in the tab.
Real ``player.js`` in node, scenarios in ``tests/web_js/player_tv_seek.js``.

Rollback (``_follow`` ignores ``seek``): ``afterSeek`` stays on 1062.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "player_tv_seek.js"


@pytest.fixture(scope="module")
def facts() -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node is missing: the scenarios run player.js in node", pytrace=False)
    done = subprocess.run(
        [node, str(RUNNER)], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    said: dict[str, Any] = json.loads(done.stdout)
    return said


def test_a_bridge_seek_back_moves_the_tab_film_to_the_tv(facts: dict[str, Any]) -> None:
    assert facts["beforeSeek"] == 1062
    assert facts["afterSeek"] == 745.1
    assert facts["seekingAfter"] is False


def test_without_a_new_seek_number_a_report_behind_the_film_is_a_tail(
    facts: dict[str, Any],
) -> None:
    assert facts["sameNumber"] == 760
    assert facts["noSeek"] == 760


def test_the_first_snapshot_of_a_cast_only_remembers_the_number(facts: dict[str, Any]) -> None:
    assert facts["firstSnapshot"] == 760


def test_a_seek_back_from_the_tv_remote_moves_the_tab_film_without_a_number(
    facts: dict[str, Any],
) -> None:
    """Пульт ТВ номера моста не несёт: обгон дальше набега рукопожатия - перемотка назад.

    Откат (``LOST_S`` не сверяется): плёнка остаётся у 1690 и лишь замедляется."""
    assert 1381.8 <= facts["remoteBack"] <= 1385.0, facts["remoteBack"]


def test_the_tv_buffer_after_a_remote_seek_is_not_counted_as_play(
    facts: dict[str, Any],
) -> None:
    """Стенд 06-10-2026: пульт «-300», ТВ 18 с в буфере на 217.8 и заиграл с того же числа,
    а вкладка засчитала буфер за ход и встала на 234.8 - на 17 с впереди ТВ.

    Откат (метка доклада держит только число): плёнка на 236.0."""
    assert 217.8 <= facts["afterBuffer"] <= 220.0, facts["afterBuffer"]


def test_back_to_the_browser_lands_on_the_report_counted_on_to_now(
    facts: dict[str, Any],
) -> None:
    """«На комп» между докладами садит вкладку на доклад плюс ход с мига, когда он заиграл.

    Прибор (пункт 10) этого больше не видит: продукт досчитывает доклад сам, и его возраст
    на чтении - доли секунды. Вкладка, садящаяся на сам доклад, отстала бы на опрос.

    Откат (``_tvPosition`` отдаёт доклад как есть): плёнка на 300.0."""
    assert 305.0 <= facts["landedHome"] <= 308.0, facts["landedHome"]
