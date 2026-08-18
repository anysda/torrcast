"""Коды возврата ``cast``: ``0`` ок, ``1`` не нашли, ``2`` инфра-ошибка.
Читают их все сценарии команд и :func:`torrcast.cli.main.main`.
"""

from typing import Final

EXIT_OK: Final = 0
EXIT_NOT_FOUND: Final = 1
EXIT_INFRA: Final = 2
