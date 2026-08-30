"""Коды возврата ``cast``: ``0`` ок, ``1`` не нашли, ``2`` инфра-ошибка, ``3`` отменено.
Читают их все сценарии команд и :func:`torrcast.cli.main.main`.
"""

from typing import Final

EXIT_OK: Final = 0
EXIT_NOT_FOUND: Final = 1
EXIT_INFRA: Final = 2
#: 🔴 TC-926. Человек снял свой вопрос сам (:class:`~torrcast.domain.cancelled_error.
#: CancelledError`). Не ноль: показа не было, и `cast ... && скажи «играю»` соврал бы.
#: Не двойка: отказа тоже не было, и тот, кто отличает отмену от аварии, обязан читать
#: именно это число, а не «любой ненулевой».
EXIT_CANCELLED: Final = 3
