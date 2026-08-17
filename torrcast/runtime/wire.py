"""Композиционный корень: назначает слоям исполнителей внешнего мира.

Единственное место, где сценарий узнаёт, КТО пишет след и кто ходит в сеть. Зовётся
один раз на процесс - точкой входа (:func:`torrcast.runtime.main.main`) и тестами,
которым нужен настоящий, а не молчащий след.
"""

from torrcast.adapters.console.console import Progress
from torrcast.adapters.filesystem.trace_journal import FileJournal
from torrcast.ports.journal import install as install_journal
from torrcast.ports.progress import install as install_progress


def wire() -> None:
    """Поставить боевых исполнителей на все порты."""
    install_journal(FileJournal())
    install_progress(Progress)
