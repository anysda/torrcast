"""Настоящее время: монотонные секунды, стенные часы и сон.

Единственный, кто в пакете зовёт :mod:`time` для ожидания; всем остальным часы
приходят портом (:class:`torrcast.ports.clock.Clock`), и подделать их можно
конструктором, а не подменой модуля.
"""

import time


class SystemClock:
    """Часы, которые идут сами."""

    def monotonic(self) -> float:
        """Монотонные секунды: считать ими разрешено только разницу."""
        return time.monotonic()

    def wall(self) -> float:
        """Стенное время: им подписываются метки, которые сводят два процесса."""
        return time.time()

    def sleep(self, seconds: float) -> None:
        """Подождать ``seconds`` секунд."""
        time.sleep(seconds)
