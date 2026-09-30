"""Служба раздач, которая умеет закрыть раздачу, не стирая её кэша на диске."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class ParkingEngine(Protocol):
    """Служба, которая закрывает раздачу, не стирая её кэша на диске.

    Снос (:meth:`TorrentEngine.drop`) стирает и кэш, а закладке он нужен: следующее
    «Продолжить» читает кусок у места с диска, а не из роя (до 30 с на стенде).
    """

    def park(self, torrent_hash: str) -> bool:
        """Закрыть раздачу, кэш оставить; молчание службы - ``False``."""
