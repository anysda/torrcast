"""Команда ``cast --upgrade``: обновить продукт до последней версии.
Зовёт её :func:`torrcast.cli.main.main`, сценарий ей собирает
:func:`torrcast.runtime.upgrade_command.upgrade_command`.
"""

from __future__ import annotations

from collections.abc import Callable

#: Кем отвечает ``cast --upgrade``. Кладёт сюда композиционный корень
#: (:mod:`torrcast.runtime.wire`): слой команд не вправе видеть ни подпроцессов,
#: которыми обновление зовёт загрузчик, ни путей, по которым тот лежит.
_SESSION: Callable[[], int]


def _configure_upgrade(session: Callable[[], int]) -> None:
    """Назначить, каким сеансом отвечает ``cast --upgrade``."""
    global _SESSION
    _SESSION = session


def upgrade(command: Callable[[], int] | None = None) -> int:
    """``cast --upgrade`` — обновить продукт до последней выпущенной версии."""
    return (_SESSION if command is None else command)()
