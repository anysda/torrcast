"""Изображает юнит показа: живость, что играет, причина темноты и остановка."""

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class FakeShowUnit:
    """Юнит без systemd: тест говорит, что он отвечает, и смотрит, что с ним сделали.

    Ответы - поля, а не подмены атрибутов модуля: тест задаёт `alive` и `playing`, а не
    знает, каким именем показ спрашивает systemd. Где ответ обязан меняться по ходу
    (порядок вызовов, счётчик обращений), для этого есть `on_key` и `on_stop`.
    """

    alive: bool = False
    reason: str = "юнит ещё идёт к картинке"
    playing: str = ""
    stops: list[int] = field(default_factory=list)
    on_stop: Callable[[], None] | None = None
    on_key: Callable[[], str] | None = None

    def active(self) -> bool:
        return self.alive

    def why(self) -> str:
        return self.reason

    def stop(self) -> None:
        self.stops.append(1)
        self.alive = False
        if self.on_stop is not None:
            self.on_stop()

    def key(self) -> str:
        return self.on_key() if self.on_key is not None else self.playing
