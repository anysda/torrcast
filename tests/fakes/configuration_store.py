"""Хранит настройки configure в памяти."""

from dataclasses import dataclass, field

from torrcast.domain.settings import Settings


@dataclass
class FakeConfigurationStore:
    settings: Settings = field(default_factory=Settings)
    saved: list[Settings] = field(default_factory=list)

    def load(self) -> Settings:
        return self.settings

    def save(self, settings: Settings) -> None:
        self.settings = settings
        self.saved.append(settings)
