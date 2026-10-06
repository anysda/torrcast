"""hls.js грузит показ, а не страница.

Файл весит 414 КБ, и его разбор стоял в ``index.html`` первым сценарием: 40 мс до
первого кадра любой страницы, прямая ссылка на карточку в том числе. Нужен он только
экрану ``/play``: там ``_attach`` дожидается файла и встаёт с последним адресом.

Раскладка - в ``tests/web_js/player_hls_lazy.js``.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "tests" / "web_js" / "player_hls_lazy.js"
PAGE = ROOT / "web" / "static" / "index.html"


@pytest.fixture(scope="module")
def stood() -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.fail("node не найден: сторож загрузки hls.js исполняет player.js", pytrace=False)
    done = subprocess.run(
        [node, str(RUNNER)], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    said: dict[str, Any] = json.loads(done.stdout)
    return said


def test_the_page_does_not_parse_hls_before_its_first_frame() -> None:
    page = PAGE.read_text(encoding="utf-8")
    assert not re.search(r"<script[^>]*hls[^>]*>", page), "hls.js снова держит первый кадр"


def test_the_player_loads_hls_once_and_attaches_the_last_stream(stood: dict[str, Any]) -> None:
    loaded = stood["loaded"]
    assert loaded["before"] == {"tags": ["/static/hls-1.5.17.min.js"], "made": 0}, loaded
    assert loaded["tags"] == 1, loaded
    assert loaded["after"] == [["/hls/second.m3u8", 7]], loaded


def test_a_failed_hls_file_falls_back_to_the_native_video(stood: dict[str, Any]) -> None:
    assert stood["failed"] == {"tags": 1, "src": "/hls/only.m3u8"}, stood["failed"]


def test_a_phone_with_only_managed_media_source_loads_hls(stood: dict[str, Any]) -> None:
    """iOS 17.1+: без hls.js закладка играла бы с начала, а запас вкладки был бы без потолка."""
    assert stood["managed"] == {"tags": ["/static/hls-1.5.17.min.js"], "src": ""}, stood["managed"]


def test_a_browser_without_any_media_source_plays_natively(stood: dict[str, Any]) -> None:
    assert stood["bare"] == {"tags": 0, "src": "/hls/old.m3u8"}, stood["bare"]


def test_the_tab_mirroring_the_tv_marks_its_pieces_and_leaves_the_head_to_the_tv(
    stood: dict[str, Any],
) -> None:
    """🔴 TC-1169: запас вкладки при «На ТВ» перепаковывал показ под себя (:mod:`hls.js`
    ``xhrSetup``). Без каста запрос уходит как есть: открывает его сам hls.js."""
    assert stood["mirror"] == {
        "tab": [],
        "tv": [["GET", "/hls/v5.m4s?mirror=1", True]],
        "query": [["GET", "/hls/v5.m4s?a=1&mirror=1", True]],
    }, stood["mirror"]
