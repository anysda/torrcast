"""``has_next`` снимка: ``True`` - серия названа, ``None`` - стык ждёт юнита, иначе ``False``.

``None`` страница читает как «серия кончилась, юнит ещё ищет» только после конца серии:
на подъёме и в простое это же значение, и там оно отказа не прячет (``web/static/player.js``).
"""

from __future__ import annotations

import pytest

from hass import next_state as module
from hass.next_state import next_state
from tests.fakes.playback_session import FakePlaybackSession


@pytest.mark.parametrize(
    ("named", "waits", "said"),
    [("rick and morty s8e2", False, True), (None, True, None), (None, False, False)],
)
def test_has_next_tells_named_waiting_and_none_apart(
    monkeypatch: pytest.MonkeyPatch, named: str | None, waits: bool, said: bool | None
) -> None:
    monkeypatch.setattr(module, "following", lambda _session: named)
    monkeypatch.setattr(module, "_waits_for_next", lambda _session: waits)
    assert next_state(FakePlaybackSession(playing=True, play_key="tv:рик")) is said
