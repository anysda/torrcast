"""Готовый ответ маршрута страницы: код, тело и то, чем их подписать."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

#: Тип тела, которым отвечают маршруты API страницы.
JSON: Final = "application/json; charset=utf-8"
#: Страница меняется вместе с продуктом, и отданный из кэша файл пережил бы правку -
#: со стороны это читается как «правка не поехала». ETag тут не заведён намеренно:
#: цена ему сверка на каждый запрос, а выигрыш в домашней сети нулевой.
NO_STORE: Final = "no-store"


@dataclass(frozen=True, slots=True)
class Answer:
    """Один ответ страницы; писать его в сокет - дело сервера, а не маршрута."""

    code: int
    body: bytes
    kind: str = JSON
    cache: str = NO_STORE
    #: Заголовки сверх обязательной тройки: карточка метит недоехавший ответ
    #: ``X-Torrcast-Partial``, чтобы страница знала, когда переспрашивать, не разбирая
    #: тело. Пусто у всех, кому нечего сказать сверху.
    extra: tuple[tuple[str, str], ...] = ()

    def headers(self) -> tuple[tuple[str, str], ...]:
        """Заголовки ответа: тип тела, срок годности, длина и то, что добавил маршрут."""
        return (
            ("Content-Type", self.kind),
            ("Cache-Control", self.cache),
            ("Content-Length", str(len(self.body))),
            *self.extra,
        )
