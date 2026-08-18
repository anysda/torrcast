"""Композиционный корень: назначает слоям исполнителей внешнего мира.

Единственное место, где сценарий узнаёт, КТО пишет след и кто ходит в сеть. Зовётся
один раз на процесс - точкой входа (:func:`torrcast.runtime.main.main`) и тестами,
которым нужен настоящий, а не молчащий след.
"""

import torrcast.adapters.prowlarr as torrent_catalogue
from torrcast.adapters.choice_environment import _configure_choice_environment
from torrcast.adapters.choice_environment import environment as choice_environment
from torrcast.adapters.chromecast.cast import make_receiver
from torrcast.adapters.chromecast.profile_detector import detector
from torrcast.adapters.console.console import Progress, ask_line
from torrcast.adapters.console.print_console import PrintConsole
from torrcast.adapters.filesystem.release_pins import pins
from torrcast.adapters.filesystem.state import FileStateStore, load_config
from torrcast.adapters.filesystem.trace_journal import FileJournal
from torrcast.adapters.health.system_health_environment import SystemHealthEnvironment
from torrcast.adapters.http_server.stream_serve import HlsServer, hls_base, start_play_unit
from torrcast.adapters.prowlarr.merge import merge
from torrcast.adapters.prowlarr.prowlarr import Prowlarr
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
    ffmpeg_pack_command,
    film_keys,
    forget_playing,
    grid_for,
    hls_dir,
    mark_playing,
    pack_start,
    playing_flag,
    warm_file,
)
from torrcast.adapters.stream_probe import (
    Supply,
    pick_video_file,
    probe,
    segment_name,
    segment_slot,
    swarm_pulse,
)
from torrcast.adapters.system_clock import CLOCK
from torrcast.adapters.systemd.transient_show_unit import TransientShowUnit
from torrcast.adapters.torrserver.contact_wait import ContactWait
from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.adapters.warm_environment import environment as warm_environment
from torrcast.ports.journal import install as install_journal
from torrcast.ports.progress import install as install_progress
from torrcast.ports.show_unit import install as install_unit
from torrcast.ports.state_store import install as install_state
from torrcast.runtime.facts_wiring import FACTS
from torrcast.runtime.menu_facts import MenuFacts
from torrcast.runtime.native_picture import native_picture
from torrcast.runtime.trace_thresholds import trace_thresholds
from torrcast.usecases.cache_reserve import _configure_cache_reserve
from torrcast.usecases.cast_command import _configure_cast_command
from torrcast.usecases.choice.configure import configure as configure_choice
from torrcast.usecases.discover import _configure_discover
from torrcast.usecases.doctor import _configure as configure_checks
from torrcast.usecases.doctor_command import _configure as configure_doctor
from torrcast.usecases.episode_duration import _configure_episode_duration
from torrcast.usecases.feed_pack import configure as configure_feed
from torrcast.usecases.playback import _configure_playback
from torrcast.usecases.rank import _cut, bitrate_of, hevc_hope, is_candidate, is_dated
from torrcast.usecases.rank import configure as configure_rank
from torrcast.usecases.reinforce import _timed
from torrcast.usecases.reinforce.configure import configure as configure_reinforce
from torrcast.usecases.releases_command import _configure_releases_command
from torrcast.usecases.revive_playback import _configure_revive_playback
from torrcast.usecases.select import _configure_select
from torrcast.usecases.select_bench import _configure_select_bench
from torrcast.usecases.torrents import _configure_torrents
from torrcast.usecases.voices_command import _configure_voices_command
from torrcast.usecases.warm import configure as configure_warm
from torrcast.usecases.worker import _configure_worker
from torrcast.usecases.worker_loop import _configure_worker_loop


def wire() -> None:
    """Поставить боевых исполнителей на все порты."""
    install_journal(FileJournal())
    install_progress(Progress)
    install_state(FileStateStore())
    install_unit(TransientShowUnit())
    # 🔴 Прогреву внешний мир приходит не портом, а мешком-средой, и раздавал его
    # побочный эффект импорта снесённого плоского фасада `torrcast/warm.py`. Фасад не
    # импортировал никто, поэтому живой показ падал на первом же обращении прогрева к
    # часам (NameError: _environment) - сразу после того, как первые куски уже уехали на
    # ТВ. Раздаёт композиция, а не то, кого случайно втянул чей-то импорт.
    configure_warm(warm_environment)
    # 🔴 Тем же порядком получает свой внешний мир и лента показа: имена сегментов,
    # пробный прогон, сборку команды ffmpeg, снятие флажка картинки и каталог перекода.
    # Прежде они появлялись в сценарии из побочного эффекта импорта совместимого фасада
    # `torrcast.stream`, который вписывал их в чужие модули через `globals().update`;
    # с его сносом (TC-682) раздача отсюда осталась единственной.
    configure_feed(
        segment_name, segment_slot, pack_start, ffmpeg_pack_command, forget_playing, RECODE_DIR
    )
    # Само окружение выбора - адаптер, и правила соседних сценариев ему не назвать
    # импортом: ранжирование, добор и справка лежат слоем выше адаптеров. Прежде оно
    # доставало их строкой с именем модуля прямо в вызове; называет их теперь корень.
    _configure_choice_environment(
        FACTS.passport.of, _cut, bitrate_of, hevc_hope, is_candidate, is_dated, _timed
    )
    # 🔴 То же и у выбора раздачи: среду раздавал импорт фасада-смертника `torrcast.choice`,
    # и беда пряталась за порядком импортов. Фасада нет, раздаёт корень (TC-630). ⚠️ Слот
    # берётся ИМЕНЕМ ИЗ МОДУЛЯ: у пакета-части плоского namespace короткое `configure`
    # затёрто одноимённой единицей ранжирования, и среда встала бы в никуда, молча.
    configure_choice(choice_environment)
    # И у ранжирования то же: печать ему раздавал импорт совместимого фасада.
    configure_rank(PrintConsole())
    # Самопроверка окружения - два разных внешних мира: чем узнавать (системная среда
    # проб) и что проверять (файл настроек). Оба приходят отсюда, а не из строки с
    # именем модуля внутри самой команды.
    configure_checks(SystemHealthEnvironment())
    configure_doctor(load_config)
    # Медиатракт: службу раздач сценарии заводят сами - адрес и срок ответа знают только
    # они, - но ЧЕМ её заводить, знает отсюда. Иначе имя `TorrServer` появлялось бы в
    # сценарии из строки, и слой показа снова ходил бы в сеть напрямую.
    _configure_cache_reserve(TorrServer)
    _configure_torrents(TorrServer)
    _configure_episode_duration(probe)
    # Стенд отбора греет раздачи параллельно: чтение паспорта, прогрев файла, признак
    # жизни роя и отсрочка первого контакта - четыре разных внешних мира, и все четыре
    # приходят отсюда. Прежде стенд доставал их строкой с именем прежнего фасада.
    _configure_select_bench(probe, warm_file, swarm_pulse, ContactWait)
    # Сам отбор ходит в службу раздач ровно один раз - за дорожками названного
    # вручную релиза, - и спрашивает человека о начале сериала заново. Служба,
    # чтение паспорта и вопрос приходят отсюда, а не из строки с именем фасада.
    _configure_select(TorrServer, probe, ask_line)
    # Поиск: сырая выдача каталога, справка о картинах и завод клиента индексеров. Все
    # трое ходят в сеть, и слою сценариев их не назвать - только корню. Добор берёт первые
    # два тем же порядком: прежде их раздавал импорт фасада-смертника `torrcast.reinforce`,
    # единственного, кто видел сразу `torrcast.search` и `torrcast.facts` (TC-632). Слот -
    # снова именем из модуля, по причине выше.
    _configure_discover(torrent_catalogue, FACTS.passport.of, Prowlarr)
    configure_reinforce(torrent_catalogue, FACTS.passport.of)
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
