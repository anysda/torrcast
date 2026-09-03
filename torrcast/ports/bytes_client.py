"""Забирает готовый файл по адресу; зовёт адаптер постера."""

from typing import Protocol


class BytesClient(Protocol):
    """Скачивает тело ответа как есть.

    Отдельно от :class:`~torrcast.ports.json_client.JsonClient` намеренно: тот разбирает
    ответ в дерево значений, а тут ответ - картинка, и разбирать в ней нечего. Одним
    договором это было бы имя, обещающее JSON и отдающее байты.
    """

    def fetch(self, address: str, timeout: float) -> bytes: ...
