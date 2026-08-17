"""Возвращает тестам паспорт медиа и запоминает источник."""

from dataclasses import dataclass, field

from torrcast.domain.media import Media


@dataclass
class FakeProber:
    result: Media
    sources: list[str] = field(default_factory=list)
    #: Сроки, с которыми у него спрашивали: своя серия ждёт ответа не столько же, сколько
    #: выбор релиза, и разницу видно только здесь.
    timeouts: list[float] = field(default_factory=list)

    def __call__(self, source_url: str, /, timeout: float = 90.0) -> Media:
        self.sources.append(source_url)
        self.timeouts.append(timeout)
        return self.result
