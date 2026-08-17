"""Композиционный корень: назначает слоям исполнителей внешнего мира.

Единственное место, где сценарий узнаёт, КТО пишет след и кто ходит в сеть. Зовётся
один раз на процесс - точкой входа (:func:`torrcast.runtime.main.main`) и тестами,
которым нужен настоящий, а не молчащий след.
"""

from torrcast.adapters.console.console import Progress
from torrcast.adapters.filesystem.state import FileStateStore
from torrcast.adapters.filesystem.trace_journal import FileJournal
from torrcast.adapters.health.system_health_environment import SystemHealthEnvironment
from torrcast.adapters.systemd.transient_show_unit import TransientShowUnit
from torrcast.adapters.warm_environment import environment as warm_environment
from torrcast.ports.journal import install as install_journal
from torrcast.ports.progress import install as install_progress
from torrcast.ports.show_unit import install as install_unit
from torrcast.ports.state_store import install as install_state
from torrcast.usecases.doctor import _configure as configure_checks
from torrcast.usecases.warm import configure as configure_warm


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
    configure_checks(SystemHealthEnvironment())
