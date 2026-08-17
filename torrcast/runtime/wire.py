"""Композиционный корень: назначает слоям исполнителей внешнего мира.

Единственное место, где сценарий узнаёт, КТО пишет след и кто ходит в сеть. Зовётся
один раз на процесс - точкой входа (:func:`torrcast.runtime.main.main`) и тестами,
которым нужен настоящий, а не молчащий след.
"""

from torrcast.adapters.filesystem.trace_journal import FileJournal
from torrcast.ports.journal import install


def wire() -> None:
    """Поставить боевых исполнителей на все порты."""
    install(FileJournal())
