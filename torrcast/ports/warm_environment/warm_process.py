"""Процесс захода упаковки в объёме, который нужен прогреву: ему шлют сигнал."""

from typing import Protocol


class WarmProcess(Protocol):
    """Процесс ffmpeg идущего захода: им прогрев замирает и оживает.

    Ровно одна ручка, и это сам договор: прогрев уступает процессор живому показу
    сигналами (:func:`torrcast.usecases.warm.throttle._throttle`), а больше ничего от
    чужого процесса не хочет - ни кода возврата, ни вывода.
    """

    def send_signal(self, number: int) -> None: ...
