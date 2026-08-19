"""Проводка показа: тут его сценарии видят медиатракт, приёмник и юнит systemd.

Зовёт её композиционный корень (:func:`torrcast.runtime.wire.wire`), и только он."""

from torrcast.adapters.chromecast.cast import make_receiver
from torrcast.adapters.chromecast.profile_detector import detector
from torrcast.adapters.filesystem.release_pins import pins
from torrcast.adapters.filesystem.state import load_config
from torrcast.adapters.http_server.stream_serve import HlsServer, hls_base, start_play_unit
from torrcast.adapters.prowlarr.merge import merge
from torrcast.adapters.prowlarr.to_releases import to_releases
from torrcast.adapters.recode import (
    MAXRATE_GAIN,
    RECODE_DIR,
    Encode,
    Recoder,
    Weights,
    whole_encode,
)
from torrcast.adapters.stream_pack import (
    film_keys,
    forget_playing,
    grid_for,
    hls_dir,
    mark_playing,
    playing_flag,
)
from torrcast.adapters.stream_probe import (
    Supply,
    pick_video_file,
    probe,
)
from torrcast.adapters.system_clock import CLOCK
from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.runtime.menu_facts import MenuFacts
from torrcast.runtime.native_picture import native_picture
from torrcast.runtime.trace_thresholds import trace_thresholds
from torrcast.usecases.cast_command import _configure_cast_command
from torrcast.usecases.playback import _configure_playback
from torrcast.usecases.releases_command import _configure_releases_command
from torrcast.usecases.revive_playback import _configure_revive_playback
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
    # диск и подпроцессы. Сценарий их только зовёт, а КЕМ они будут, знает корень: пока
    # эти имена приходили строкой с именем модуля, слой показа ходил в адаптеры сам.
    _configure_playback(
        CLOCK,
        make_receiver,
        probe,
        detector.detect,
        pick_video_file,
        hls_dir,
        hls_base,
        playing_flag,
        forget_playing,
        start_play_unit,
        film_keys,
        grid_for,
        HlsServer,
        Encode,
        Recoder,
        Weights.of,
        whole_encode,
        MAXRATE_GAIN,
        RECODE_DIR,
    )
