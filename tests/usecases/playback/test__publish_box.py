"""Зеркало: ящик вкладки за приёмник, который сам о себе так не расскажет (TC-1224)."""

from __future__ import annotations

from pathlib import Path

import pytest

import torrcast.usecases.playback._show_state as _state
from tests.fakes.receiver import FakeReceiver
from torrcast.domain.config import Config
from torrcast.domain.position import Position
from torrcast.domain.profile import CAUTIOUS
from torrcast.usecases.playback._publish_box import _publish_box


def test_a_non_browser_receiver_gets_the_box_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(_state, "publish_box", lambda *args: calls.append(args))
    config = Config(recode=False, warm=False)
    receiver = FakeReceiver(Position(0.0, 0.0))

    _publish_box(config, receiver, tmp_path, "http://x/index.m3u8", "«Кино»", 12.0, CAUTIOUS)

    assert len(calls) == 1
    out, url, about, start, key, profile_key, container, tv = calls[0]
    assert (out, url, about, start) == (tmp_path, "http://x/index.m3u8", "«Кино»", 12.0)
    assert key and profile_key == CAUTIOUS.key and container and tv is True


def test_the_browser_receiver_is_left_to_publish_its_own_box(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Браузер кладёт ящик сам (:meth:`BrowserReceiver.play`) - второй записи тут нет.

    Без сторожки ``config.receiver == "browser"`` тот же вызов ушёл бы дважды: раз - за
    показ, раз - за саму вкладку, с двумя РАЗНЫМИ ключами сеанса подряд.
    """
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(_state, "publish_box", lambda *args: calls.append(args))
    config = Config(recode=False, warm=False, receiver="browser")
    receiver = FakeReceiver(Position(0.0, 0.0))

    _publish_box(config, receiver, tmp_path, "http://x/index.m3u8", "«Кино»", 12.0, CAUTIOUS)

    assert calls == []
