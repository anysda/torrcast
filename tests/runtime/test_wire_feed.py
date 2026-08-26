"""Проводка ленты показа: после неё в слотах ленты стоит настоящий медиатракт."""

from __future__ import annotations

import time

import torrcast.usecases.feed_pack._state as _state
from torrcast.adapters.filesystem.remove_tree import remove_tree
from torrcast.adapters.recode.recode_dir import RECODE_DIR
from torrcast.adapters.side_thread import side_thread
from torrcast.adapters.stream_pack._segment_files import _paths
from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.forget_playing import forget_playing
from torrcast.adapters.stream_pack.lay_head import lay_head
from torrcast.adapters.stream_pack.packer import Packer
from torrcast.adapters.stream_pack.settle_start import settle_start
from torrcast.adapters.stream_probe.segment_name import segment_name
from torrcast.adapters.stream_probe.segment_slot import segment_slot
from torrcast.runtime.wire_feed import wire_feed


def test_the_feed_gets_the_real_packer_and_the_real_chores() -> None:
    """Каждый слот ленты занят ТЕМ САМЫМ адаптером, а не однофамильцем той же арности.

    Живое приложение проводит ленту на запуске (``tests.conftest._wired``), поэтому
    повторный вызов тут только подтверждает: слот берёт своё значение отсюда.

    🔴 Сверяется САМО значение (``is``), а не то, что его можно позвать. Стенд ленты
    заполняет те же слоты сам (:func:`tests.usecases.feed_pack.world.tract`), и потому
    ни одна проба пакета корня не спрашивает: подменённый в проводке слот весь набор
    проходит зелёным - живая проба с пустышкой ``lambda _piece, _out: None`` на месте
    укладки заголовка так и держала набор зелёным. Пустышка нужной арности договору
    порта отвечает не хуже настоящего адаптера, а разница видна только на живом показе.

    Полноту этого списка держит не память, а сторож гейта (``scripts/test-gate``): он
    сам сличает доводы, которые кладёт :func:`wire_feed`, с тем, что сверяет зеркало,
    и новый слот без сверки по значению не пропустит.
    """
    wire_feed()

    assert _state.segment_name is segment_name
    assert _state.segment_slot is segment_slot
    assert _state.settle_start is settle_start
    assert _state.ffmpeg_pack_command is ffmpeg_pack_command
    assert _state.Packer is Packer
    assert _state.forget_playing is forget_playing
    assert _state.RECODE_DIR is RECODE_DIR
    assert _state.lay_head is lay_head
    assert _state.remove_tree is remove_tree
    assert _state.segment_paths is _paths
    assert _state.clock_port is time
    assert _state.spawn is side_thread
