"""Композиционный корень: назначает слоям исполнителей внешнего мира.

Единственное место, где сценарий узнаёт, КТО пишет след и кто ходит в сеть. Зовётся
один раз на процесс - точкой входа (:func:`torrcast.runtime.main.main`) и тестами,
которым нужен настоящий, а не молчащий след.
"""

from torrcast.adapters.chromecast.cast import make_receiver
from torrcast.adapters.chromecast.profile_detector import detector
from torrcast.adapters.console.console import Progress
from torrcast.adapters.filesystem.state import FileStateStore, load_config
from torrcast.adapters.filesystem.trace_journal import FileJournal
from torrcast.adapters.health.system_health_environment import SystemHealthEnvironment
from torrcast.adapters.stream_probe import Supply, probe
from torrcast.adapters.systemd.transient_show_unit import TransientShowUnit
from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.adapters.warm_environment import environment as warm_environment
from torrcast.ports.journal import install as install_journal
from torrcast.ports.progress import install as install_progress
from torrcast.ports.show_unit import install as install_unit
from torrcast.ports.state_store import install as install_state
from torrcast.runtime.trace_thresholds import trace_thresholds
from torrcast.usecases.cache_reserve import _configure_cache_reserve
from torrcast.usecases.doctor import _configure as configure_checks
from torrcast.usecases.doctor_command import _configure as configure_doctor
from torrcast.usecases.episode_duration import _configure_episode_duration
from torrcast.usecases.torrents import _configure_torrents
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
    # побочный эффект импорта совместимого фасада `torrcast.warm`. Фасад не импортирует
    # никто, поэтому живой показ падал на первом же обращении прогрева к часам
    # (NameError: _environment) - сразу после того, как первые куски уже уехали на ТВ.
    # Раздаёт композиция, а не то, кого случайно втянул чей-то импорт.
    configure_warm(warm_environment)
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
    # Юнит показа поднимает systemd, а не CLI: свой внешний мир он получает здесь же и
    # целиком, иначе показ узнавал бы имя `TorrServer` из строки уже внутри юнита.
    _configure_worker(TorrServer, make_receiver, Supply, load_config, detector.detect)
    _configure_worker_loop(trace_thresholds)
