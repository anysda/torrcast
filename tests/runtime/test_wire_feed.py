"""Проводка ленты показа: после неё в слотах ленты стоит настоящий медиатракт."""

from __future__ import annotations

import torrcast.usecases.feed_pack._state as _state
from torrcast.adapters.filesystem.remove_tree import remove_tree
from torrcast.adapters.stream_pack._segment_files import _paths
from torrcast.adapters.stream_pack.lay_head import lay_head
from torrcast.adapters.stream_pack.packer import Packer
from torrcast.runtime.wire_feed import wire_feed


def test_the_feed_gets_the_real_packer_and_the_real_chores() -> None:
    """Завод прогона в слоте - тот самый класс медиатракта, а не однофамилец.

    Живое приложение проводит ленту на запуске (``tests.conftest._wired``), поэтому
    повторный вызов тут только подтверждает: слот берёт своё значение отсюда.

    🔴 Сверяется САМО значение, а не то, что его можно позвать. Стенд ленты заполняет
    те же слоты сам (:func:`tests.usecases.feed_pack.world.tract`), и потому ни одна
    проба пакета корня не спрашивает: подменённый здесь слот весь набор проходит
    зелёным. Пустышка нужной арности договору порта отвечает не хуже настоящего
    адаптера, а разница видна только на живом показе.
    """
    wire_feed()

    assert _state.Packer is Packer
    assert _state.segment_name(3) == "v3.ts"
    assert _state.lay_head is lay_head
    assert _state.remove_tree is remove_tree
    assert _state.segment_paths is _paths
