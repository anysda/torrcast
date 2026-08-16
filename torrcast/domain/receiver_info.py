"""Identity of a playback receiver discovered on the local network."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReceiverInfo:
    """Stable receiver details required to select and connect to it."""

    name: str
    address: str
    model: str = ""

    @property
    def title(self) -> str:
        """Как назвать пункт меню: имя, за неимением - модель, за неимением - «приёмник».

        Безымянный пункт всё равно выбираем: адрес рядом, и человек узнаёт свой
        телевизор по нему. Пустая строка в меню была бы хуже честного «приёмник».
        """
        return self.name or self.model or "приёмник"
