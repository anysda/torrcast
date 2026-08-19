"""Добирает справку к меню из внешних источников; зовёт сценарий меню франшизы."""

from collections.abc import Callable
from typing import Protocol

from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.settings import HTTP_TIMEOUT


class BlurbSource(Protocol):
    """``ready`` получает описания сразу, как приехали, - не дожидаясь украшений.

    Второй элемент ответа - про какие картины источник РЕАЛЬНО ответил: неполный ответ
    не говорит про промолчавшую часть ничего, и «статьи нет» про неё - выдумка.
    """

    def fetch(
        self,
        wanted: list[tuple[str, int | None]],
        timeout: float = HTTP_TIMEOUT,
        ready: Callable[[dict[tuple[str, int | None], Fact]], None] | None = None,
    ) -> tuple[dict[tuple[str, int | None], Fact], set[tuple[str, int | None]]]: ...
