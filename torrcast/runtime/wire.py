"""Композиционный корень: назначает слоям исполнителей внешнего мира.

Единственное место, где сценарий узнаёт, КТО пишет след и кто ходит в сеть. Зовётся
один раз на процесс - точкой входа (:func:`torrcast.runtime.main.main`) и тестами,
которым нужен настоящий, а не молчащий след.
"""

from torrcast.adapters.console.console.progress import Progress
from torrcast.adapters.filesystem.state.file_state_store import FileStateStore
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.filesystem.trace_journal.file_journal import FileJournal
from torrcast.adapters.health.system_health_environment import SystemHealthEnvironment
from torrcast.adapters.systemd.transient_show_unit import TransientShowUnit
from torrcast.adapters.warm_environment import environment as warm_environment
from torrcast.ports.journal.slot import install as install_journal
from torrcast.ports.progress.slot import install as install_progress
from torrcast.ports.show_unit.slot import install as install_unit
from torrcast.ports.state_store.slot import install as install_state
from torrcast.runtime.configure_cli import configure_cli
from torrcast.runtime.wire_feed import wire_feed
from torrcast.runtime.wire_search import wire_search
from torrcast.runtime.wire_show import wire_show
from torrcast.usecases.doctor import _configure as configure_checks
from torrcast.usecases.doctor_command import _configure as configure_doctor
from torrcast.usecases.warm.configure import configure as configure_warm


def wire() -> None:
    """Поставить боевых исполнителей на все порты."""
    # Слой команд не видит ни адаптеров, ни сборки сеансов: режим stdin и три собранные
    # команды приходят к нему отсюда (:mod:`torrcast.runtime.configure_cli`).
    configure_cli()
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
    # Тем же порядком получает свой внешний мир и лента показа.
    wire_feed()
    # Самопроверка окружения - два разных внешних мира: чем узнавать (системная среда
    # проб) и что проверять (файл настроек). Оба приходят отсюда, а не из строки с
    # именем модуля внутри самой команды.
    configure_checks(SystemHealthEnvironment())
    configure_doctor(load_config)
    # Поиск картины и отбор раздачи получают свой внешний мир тем же порядком
    # (:mod:`torrcast.runtime.wire_search`), а весь показ - своим
    # (:mod:`torrcast.runtime.wire_show`): корню тут остаются порты процесса и справка.
    wire_search()
    wire_show()
