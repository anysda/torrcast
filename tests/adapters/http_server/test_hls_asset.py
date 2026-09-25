"""Проверяет общую границу имён прямой и веб-раздачи HLS."""

import pytest

from torrcast.adapters.http_server.hls_asset import HLS_ASSET


@pytest.mark.parametrize(
    "name", ["v0.ts", "v137.ts", "v2.m4s", "init.mp4", "index.m3u8", "stream.m3u8"]
)
def test_the_grid_of_the_show_is_served(name: str) -> None:
    assert HLS_ASSET.fullmatch(name), f"{name} - это манифест или сегмент сетки"


@pytest.mark.parametrize(
    "name", ["../state.json", "v1.ts/../../etc/passwd", "index.m3u8?x=1", "", "v.ts", "source.mp4"]
)
def test_nothing_but_the_grid_is_served(name: str) -> None:
    """Каталог наружу не открыт: имя вне сетки - 404, а не файл с диска."""
    assert not HLS_ASSET.fullmatch(name), f"{name} уехал бы наружу"
