"""Голова упаковки идёт за местом ТВ, а не за вкладкой-зеркалом каста (TC-1169).

Стенд 06-10-2026: ТВ мотают назад, вкладка при «На ТВ» ещё дотягивает свой запас у старого
места. Тех кусков уже нет (уборка стёрла их вслед за ТВ), запрос не «позади зрителя», и
упаковка перезапускалась под вкладку - уводя голову от того, что смотрит ТВ. Запрос зеркала
помечен (``?mirror=1``, ставит ``player.js``) и ждёт файла, не двигая упаковку.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from tests.conftest import free_port
from torrcast.adapters.http_server.hls_server import HlsServer
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.hls_dir import hls_dir
from torrcast.usecases.feed_pack.feed import Feed


def _serve(tmp_path: Path) -> tuple[HlsServer, list[int]]:
    started: list[int] = []

    class Counted(Feed):
        def restart(self, slot: int) -> None:
            started.append(slot)

    out = hls_dir(str(tmp_path / "hls"))
    feed = Counted(source="", audio=0, out=out, grid=Grid.uniform(7200.0), wait=0.0)
    server = HlsServer(out, port=free_port(), feed=feed)
    server.start()
    return server, started


@pytest.mark.machine
def test_the_mirror_tab_does_not_move_the_packing_head(tmp_path: Path) -> None:
    server, started = _serve(tmp_path)
    try:
        base = f"http://127.0.0.1:{server.port}"
        mirror = requests.get(f"{base}/v50.ts?mirror=1", timeout=10)
        assert started == [], "запас вкладки-зеркала увёл голову упаковки от ТВ"
        assert mirror.status_code == 404, "куска нет - зеркало ждёт, а не выдумывает"

        requests.get(f"{base}/v60.ts", timeout=10)
        assert started == [60], "запрос самого ТВ обязан перематывать упаковку"
    finally:
        server.stop()
