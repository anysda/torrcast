"""🔴 Отказ круга словом, пришедший на скелет превью, обязан встать на экран.

Карточка, открытая прямой ссылкой, получает скелет первым ответом и слово «ищем
раздачи» вместе с ним. Отказ круга приходит следующим ответом на пустое тело - и
отбрасывался, если тело уже стояло: опрос кончался, а слово оставалось навсегда.

Раскладка - в ``tests/web_js/card_refused.js``, сюда приезжает только то, что встало.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "card_refused.js"


@pytest.fixture(scope="module")
def stood() -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node не найден: сторож отказа карточки исполняет card.js", pytrace=False)
    done = subprocess.run(
        [node, str(RUNNER)], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    said: dict[str, Any] = json.loads(done.stdout)
    return said


def test_a_refusal_after_a_preview_skeleton_replaces_the_word_with_the_reason(
    stood: dict[str, Any],
) -> None:
    assert stood["onSkeleton"]["error"] == "not_found", (
        f"отказ на скелете отброшен, ожидание осталось без конца: {stood['onSkeleton']}"
    )
    assert stood["onSkeleton"]["refused"] == "Prowlarr не отвечает", stood["onSkeleton"]
    assert stood["onSkeleton"]["searching"] is False, "слово «ищем раздачи» осталось на экране"
    assert stood["onSkeleton"]["title"] == "Престиж", (
        f"отказ по прямой ссылке стёр имя картины: {stood['onSkeleton']}"
    )


def test_a_refusal_on_an_empty_body_still_speaks_the_same_reason(stood: dict[str, Any]) -> None:
    assert stood["onEmpty"]["error"] == "not_found", stood["onEmpty"]
    assert stood["onEmpty"]["refused"] == "Prowlarr не отвечает", stood["onEmpty"]
