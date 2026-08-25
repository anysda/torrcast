"""Зеркало конца по воле зрителя: закрытый с пульта показ не воскрешается."""

from __future__ import annotations

import pytest

from torrcast.domain.position import Position
from torrcast.usecases.revive_playback._closed import _closed


def test_a_show_the_receiver_still_holds_is_not_closed_by_anyone() -> None:
    """Показ на экране - закрывать нечего, и молчим об этом."""
    assert _closed(Position(2231.0, 7200.0, True, "PLAYING"), "[сеанс 1]", 2231.0) is False


def test_a_dark_screen_of_our_own_accident_is_not_the_viewers_will() -> None:
    """Погасший показ сам по себе волей зрителя не является: его поднимает лестница."""
    assert _closed(Position(0.0, 7200.0, False, "IDLE"), "[сеанс 1]", 2231.0) is False


def test_the_show_closed_by_the_viewer_is_named_aloud_and_not_raised(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Закрытый зрителем показ кончается, и место его называется вслух.

    Молчаливый конец тут неотличим от нашей аварии: зритель обязан видеть, что показ
    свернули по его же команде, а не потеряли.
    """
    closed = Position(0.0, 7200.0, False, "UNKNOWN", closed=True)

    assert _closed(closed, "[сеанс 1]", 5981.0) is True

    out = capsys.readouterr().out
    assert "показ закрыт с пульта на 1:39:41" in out
    assert "поднимать не буду" in out
