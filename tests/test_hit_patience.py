"""Зеркало :data:`hass.hit_claims._PATIENCE`: шторм 429 дольше трёх тишин - не промах.

На стенде шторм на 15 с после первого вопроса истории: история спросила картины трижды, все
три ответа пришли в тишину 429, и третий записал настоящий промах на пять минут. Страница
перестала переспрашивать историю на 17-й секунде, ряд «Продолжить» остался без обложек.
"""

from __future__ import annotations

from pathlib import Path

from hass.hit_claims import _ATTEMPTS, _PATIENCE
from hass.hit_posters import FIELD
from tests.test_hit_claims import _Clock, _posters, _Storm
from tests.test_hit_posters import FakeSource, _row

#: Тишина после 429 у справки, секунды (``QUIET_AFTER_429``).
_QUIET = 5.0


def test_a_storm_longer_than_three_silences_still_brings_the_cover(tmp_path: Path) -> None:
    source, clock, storm = FakeSource(pages={}), _Clock(), _Storm()
    posters = _posters(tmp_path, source, clock, storm)
    began = clock.now
    while len(source.judged) < _ATTEMPTS + 2:
        storm.calm = clock.now + _QUIET
        posters.offer([_row()])
        clock.now = storm.calm
        assert posters.pending([_row()]), f"ряд перестали ждать через {clock.now - began} с"
    assert clock.now - began < _PATIENCE
    storm.troubled, source.pages = False, {"Тачки": ["Cars"]}
    assert posters.due([_row()]), "шторм кончился, а картину не спрашивают снова"
    assert FIELD in posters.offer([_row()])[0]  # type: ignore[operator]
