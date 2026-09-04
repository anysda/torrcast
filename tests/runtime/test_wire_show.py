"""Проводка показа: после неё в слотах показа стоят настоящий медиатракт и приёмник."""

from __future__ import annotations

import torrcast.usecases.cast_command._play_state as _play_state
import torrcast.usecases.playback._show_state as _show_state
import torrcast.usecases.releases_command as _releases_command
import torrcast.usecases.revive_playback._revive_state as _revive_state
import torrcast.usecases.voices_command as _voices_command
import torrcast.usecases.worker as _worker
import torrcast.usecases.worker_loop as _worker_loop
from torrcast.adapters.chromecast.cast.make_receiver import make_receiver
from torrcast.adapters.chromecast.profile_detector import detector
from torrcast.adapters.filesystem.release_pins import pins
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.http_server.hls_base import hls_base
from torrcast.adapters.http_server.hls_server import HlsServer
from torrcast.adapters.prowlarr.merge import merge
from torrcast.adapters.prowlarr.to_releases import to_releases
from torrcast.adapters.recode.encode import Encode
from torrcast.adapters.recode.encode_settings import MAXRATE_GAIN
from torrcast.adapters.recode.recode_dir import RECODE_DIR
from torrcast.adapters.recode.recoder import Recoder
from torrcast.adapters.recode.weights import Weights
from torrcast.adapters.recode.whole_encode import whole_encode
from torrcast.adapters.stream_pack.forget_playing import forget_playing
from torrcast.adapters.stream_pack.grid_for import grid_for
from torrcast.adapters.stream_pack.hls_dir import hls_dir
from torrcast.adapters.stream_pack.mark_playing import mark_playing
from torrcast.adapters.stream_pack.playing_flag import playing_flag
from torrcast.adapters.stream_probe.pick_video_file import pick_video_file
from torrcast.adapters.stream_probe.probe import probe
from torrcast.adapters.stream_probe.supply import Supply
from torrcast.adapters.system_clock import CLOCK
from torrcast.adapters.systemd.start_play_unit import start_play_unit
from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.runtime.facts_wiring import FACTS
from torrcast.runtime.menu_facts import MenuFacts
from torrcast.runtime.native_picture import native_picture
from torrcast.runtime.trace_thresholds import trace_thresholds
from torrcast.runtime.wire_show import wire_show


def test_the_show_gets_the_real_media_pipeline_and_the_real_receiver() -> None:
    """Каждый слот показа занят ТЕМ САМЫМ адаптером, а не однофамильцем той же арности.

    Живое приложение проводит показ на запуске (``tests.conftest._wired``), поэтому
    повторный вызов тут только подтверждает: слот берёт своё значение отсюда.

    🔴 Сверяется САМО значение, а не то, что его можно позвать: пустышка нужной арности
    договору порта отвечает не хуже настоящего адаптера - живая проба с подменённым
    слотом держала весь набор зелёным, и разница была видна только на живом показе.
    Ручки экземпляров (``detector.detect``, ``pins.recalled``, ``Weights.of``) собираются
    заново на каждое обращение, поэтому они сверяются через ``==``: у связанного метода
    равенство - это тот же ``__self__`` и та же ``__func__``, а ``is`` не держал бы и
    настоящее значение.

    Полноту этого списка держит не память, а сторож гейта (``scripts/test-gate``): он
    сам сличает доводы, которые кладёт :func:`wire_show`, с тем, что сверяет зеркало,
    и новый слот без сверки по значению не пропустит.
    """
    wire_show()

    # Среда показа целиком: медиатракт, приёмник, часы и юнит (ShowEnvironment).
    assert _show_state.CLOCK is CLOCK
    assert _show_state.make_receiver is make_receiver
    assert _show_state.probe is probe
    assert _show_state.detect_profile == detector.detect
    assert _show_state.pick_video_file is pick_video_file
    assert _show_state.hls_dir is hls_dir
    assert _show_state.hls_base is hls_base
    assert _show_state.playing_flag is playing_flag
    assert _show_state.forget_playing is forget_playing
    assert _show_state.start_play_unit is start_play_unit
    assert _show_state.grid_for is grid_for
    assert _show_state.HlsServer is HlsServer
    assert _show_state.Encode is Encode
    assert _show_state.Recoder is Recoder
    assert _show_state.weights_of == Weights.of
    assert _show_state.flat_weights == Weights.flat
    assert _show_state.whole_encode is whole_encode
    assert _show_state.MAXRATE_GAIN is MAXRATE_GAIN
    assert _show_state.RECODE_DIR is RECODE_DIR

    # Юнит показа и его цикл.
    assert _worker._worker_engines is TorrServer
    assert _worker._worker_receivers is make_receiver
    assert _worker._worker_sources is Supply
    assert _worker._worker_configs is load_config
    assert _worker._worker_detect == detector.detect
    assert _worker_loop._worker_thresholds is trace_thresholds

    # Команды cast: показ, таблица релизов и меню озвучек.
    assert _play_state._play_engines is TorrServer
    assert _play_state._play_settings is load_config
    assert _play_state._play_detect == detector.detect
    assert _play_state._play_facts is MenuFacts
    assert _play_state._play_native is native_picture
    assert _play_state._play_pinned == pins.recalled
    assert _play_state._play_merge is merge
    assert _play_state._play_releases is to_releases
    assert _play_state._play_origin == FACTS.cache.read
    assert _releases_command._releases_settings is load_config
    assert _releases_command._releases_facts is MenuFacts
    assert _releases_command._releases_detect == detector.detect
    assert _releases_command._releases_remember == pins.remember
    assert _voices_command._voices_settings is load_config
    assert _voices_command._voices_engines is TorrServer
    assert _voices_command._voices_native is native_picture

    # Оживление погасшего показа.
    assert _revive_state._revive_clock is CLOCK
    assert _revive_state._revive_playing_mark is mark_playing
