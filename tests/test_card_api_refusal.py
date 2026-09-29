"""Отказ круга от сервера до строки карточки: ``circle_refusal`` -> ``TCApi.card`` -> ``TC.say``.

Сервер отвечает 409 кодом ``search_refused`` и причиной (ключ и значения). Страница обязана
нарисовать причину английским каталогом, а не показать код и не потерять ``whole``.
Раскладка - в ``tests/web_js/card_api_refusal.js``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from torrcast.domain.catalogs.web.en import en
from torrcast.domain.infra_error import InfraError
from torrcast.domain.search_refusal_error import SearchRefusalError
from torrcast.domain.torrcast_error import TorrcastError
from web.circle_refusal import circle_refusal

RUNNER = Path(__file__).resolve().parent / "web_js" / "card_api_refusal.js"


def _card(failed: TorrcastError, whole: bool) -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node не найден: сторож отказа карточки исполняет api.js", pytrace=False)
    answer = circle_refusal(failed, whole)
    sent = json.dumps({"status": answer.code, "body": json.loads(answer.body)})
    done = subprocess.run(
        [node, str(RUNNER), sent, json.dumps(en())],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    said: dict[str, Any] = json.loads(done.stdout)
    return said


def test_a_named_refusal_reaches_the_card_as_its_english_phrase() -> None:
    failed = SearchRefusalError(
        "discover.no_season_releases",
        "web.search.no_season_releases",
        title="Wednesday",
        season=9,
    )
    said = _card(failed, whole=True)
    assert said["text"] == "“Wednesday”: no releases with season 9", said
    assert said["whole"] is True, said


def test_an_unnamed_failure_reaches_the_card_as_the_generic_phrase() -> None:
    said = _card(InfraError("индексеры не отвечают"), whole=True)
    assert said["text"] == en()["web.search.failed"], said
    assert said["whole"] is False, said
