"""Описывает файл внутри торрент-раздачи."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TorrFile:
    index: int
    name: str
    size: int = 0

    @property
    def base(self) -> str:
        """Имя без пути: сезон живёт в каталоге, номер серии — в имени файла."""
        return self.name.replace("\\", "/").rsplit("/", 1)[-1]
