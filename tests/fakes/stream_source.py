"""Изображает для тестов источник показа и отвечает заранее назначенной бедой."""

from dataclasses import dataclass, field


@dataclass
class FakeStreamSource:
    torrent_hash: str = ""
    magnet: str = ""
    lost: str = ""
    restored: bool = False
    #: Что источник ответит на вопрос «что с тобой»; пусто - он в порядке.
    trouble: str = ""
    #: Сколько раз его спросили: вопрос стоит двух запросов к службе, и горячий путь
    #: показа не вправе его задавать.
    checks: list[str] = field(default_factory=list)

    def check(self) -> str:
        self.checks.append(self.torrent_hash)
        return self.trouble
