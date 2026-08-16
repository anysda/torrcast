"""Возвращает тестам настройки и считает их загрузки."""

from dataclasses import dataclass

from torrcast.domain.settings import Settings


@dataclass
class FakeConfigurationSource:
    settings: Settings
    load_count: int = 0

    def load(self) -> Settings:
        self.load_count += 1
        return self.settings
