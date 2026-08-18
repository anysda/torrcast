"""Идущий заход упаковки в объёме, который нужен прогреву."""

from typing import Protocol

from torrcast.ports.warm_environment.warm_process import WarmProcess


class WarmPack(Protocol):
    """Заход упаковки, пока он идёт: что уже выложено, жив ли он и как его погасить."""

    @property
    def edge(self) -> int:
        """Последний ВЫЛОЖЕННЫЙ наружу сегмент; до первой выкладки - меньше первого."""

    @property
    def proc(self) -> WarmProcess:
        """Процесс ffmpeg этого захода: прогрев уступает им процессор живому показу."""

    def publish(self) -> None:
        """Переименовать дописанные куски наружу: недописанный наружу не выходит."""

    def poll(self) -> int | None:
        """Код возврата ffmpeg; ``None`` - заход ещё идёт."""

    def stop(self, keep_files: bool = False, reason: str = "") -> None:
        """Погасить заход. Прогрев гасит с ``keep_files``: уложенное на диске остаётся."""
