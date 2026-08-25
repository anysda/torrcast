"""Проводка показа: тут его сценарии видят медиатракт, приёмник и юнит systemd.

Зовёт её композиционный корень (:func:`torrcast.runtime.wire.wire`), и только он."""

from torrcast.adapters.chromecast.cast.make_receiver import make_receiver
from torrcast.adapters.chromecast.profile_detector import detector
from torrcast.adapters.filesystem.release_pins import pins
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.http_server.stream_serve import HlsServer, hls_base, start_play_unit
from torrcast.adapters.prowlarr.merge import merge
from torrcast.adapters.prowlarr.to_releases import to_releases
from torrcast.adapters.recode.encode import Encode
from torrcast.adapters.recode.encode_settings import MAXRATE_GAIN
from torrcast.adapters.recode.recode_dir import RECODE_DIR
from torrcast.adapters.recode.recoder import Recoder
from torrcast.adapters.recode.weights import Weights
from torrcast.adapters.recode.whole_encode import whole_encode
from torrcast.adapters.stream_pack.film_keys import film_keys
from torrcast.adapters.stream_pack.forget_playing import forget_playing
from torrcast.adapters.stream_pack.grid_for import grid_for
from torrcast.adapters.stream_pack.hls_dir import hls_dir
from torrcast.adapters.stream_pack.mark_playing import mark_playing
from torrcast.adapters.stream_pack.playing_flag import playing_flag
from torrcast.adapters.stream_probe.pick_video_file import pick_video_file
from torrcast.adapters.stream_probe.probe import probe
from torrcast.adapters.stream_probe.supply import Supply
from torrcast.adapters.system_clock import CLOCK
from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.runtime.menu_facts import MenuFacts
from torrcast.runtime.native_picture import native_picture
from torrcast.runtime.trace_thresholds import trace_thresholds
from torrcast.usecases.cast_command._play_state import _configure_cast_command
from torrcast.usecases.playback._show_state import _configure_playback
from torrcast.usecases.playback.show_environment import ShowEnvironment
from torrcast.usecases.releases_command import _configure_releases_command
from torrcast.usecases.revive_playback._revive_state import _configure_revive_playback
from torrcast.usecases.voices_command import _configure_voices_command
from torrcast.usecases.worker import _configure_worker
from torrcast.usecases.worker_loop import _configure_worker_loop


def wire_show() -> None:
    """Отдать показу его внешний мир: приёмник, упаковку, кодировщики и команды ``cast``."""
    # Юнит показа поднимает systemd, а не CLI: свой внешний мир он получает здесь же и
    # целиком, иначе показ узнавал бы имя `TorrServer` из строки уже внутри юнита.
    _configure_worker(TorrServer, make_receiver, Supply, load_config, detector.detect)
    _configure_worker_loop(trace_thresholds)
    # Команды ``cast`` берут свой внешний мир тем же порядком: службу раздач, настройки,
    # паспорт приёмника, справку о картинах, происхождение картины, память показанной
    # таблицы и разбор сырой выдачи каталога. Имён этих в сценариях больше нет ни строкой.
    _configure_cast_command(
        TorrServer,
        load_config,
        detector.detect,
        MenuFacts,
        native_picture,
        pins.recalled,
        merge,
        to_releases,
    )
    _configure_releases_command(load_config, MenuFacts, detector.detect, pins.remember)
    _configure_voices_command(load_config, TorrServer, native_picture)
    # Оживление погасшего показа меряет темноту настоящими секундами и кладёт флажок
    # картинки настоящим файлом. Обоих сценарий не знает: часы и отметку даёт корень.
    _configure_revive_playback(CLOCK, mark_playing)
    # Весь медиатракт показа - упаковка, раздача, оба кодировщика и приёмник - это сеть,
    # диск и подпроцессы. Сценарий их только зовёт, а КЕМ они будут, знает корень, и
    # говорит это одним договором: каждый слот назван, и перепутать местами два слота
    # одного рода при сборке нечем.
    _configure_playback(
        ShowEnvironment(
            clock=CLOCK,
            receivers=make_receiver,
            prober=probe,
            detect=detector.detect,
            video_pick=pick_video_file,
            out_dir=hls_dir,
            base_url=hls_base,
            flag=playing_flag,
            forget_flag=forget_playing,
            start_unit=start_play_unit,
            keys=film_keys,
            grid=grid_for,
            server=HlsServer,
            encode=Encode,
            recoder=Recoder,
            weights=Weights.of,
            flat=Weights.flat,
            whole=whole_encode,
            maxrate_gain=MAXRATE_GAIN,
            recode_dir=RECODE_DIR,
        )
    )
