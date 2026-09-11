"""Зеркало :mod:`torrcast.domain.playing_where`: строка показа называет, где он идёт."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.catalogs.tongue import _choose_tongue, tongue
from torrcast.domain.playing_where import playing_where


@pytest.fixture(autouse=True)
def _restore() -> Iterator[None]:
    before = tongue()
    yield
    _choose_tongue(before)


@pytest.mark.parametrize(
    ("lang", "tab", "tv"),
    [
        ("en", "playing “Dune” - browser (this computer)   (start 9 s)", "playing “Dune” - on TV"),
        ("ru", "играю “Dune” - браузер (этот компьютер)   (старт 9 с)", "играю “Dune” - на ТВ"),
    ],
)
def test_the_tab_show_is_not_called_a_tv_show(lang: str, tab: str, tv: str) -> None:
    """🔴 Показ во вкладке писал в журнал «на ТВ» (TC-1203); показ на ТВ пишет как раньше."""
    _choose_tongue(lang)

    in_tab = phrase("playback.now_playing", about="“Dune”", secs="9", where=playing_where(True))
    on_tv = phrase("playback.now_playing", about="“Dune”", secs="9", where=playing_where(False))

    assert in_tab == tab
    assert on_tv.startswith(tv)
