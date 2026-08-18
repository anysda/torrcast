"""Проводка ленты показа: после неё в слотах ленты стоит настоящий медиатракт."""

from __future__ import annotations

import torrcast.usecases.feed_pack._state as _state
from torrcast.adapters.stream_pack.packer import Packer
from torrcast.runtime.wire_feed import wire_feed


def test_the_feed_gets_the_real_packer_and_the_real_chores() -> None:
    """Завод прогона в слоте - тот самый класс медиатракта, а не однофамилец.

    Живое приложение проводит ленту на запуске (``tests.conftest._wired``), поэтому
    повторный вызов тут только подтверждает: слот берёт своё значение отсюда.
    """
    wire_feed()

    assert _state.Packer is Packer
    assert _state.segment_name(3) == "v3.ts"
    assert callable(_state.remove_tree) and callable(_state.segment_paths)
