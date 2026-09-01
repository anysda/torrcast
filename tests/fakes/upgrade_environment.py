"""Изображает окружение обновления: права, загрузчик и передачу работы ему."""

from dataclasses import dataclass, field


@dataclass
class FakeUpgradeEnvironment:
    root: bool = True
    installed_loader: str = "/opt/torrcast/install"
    result: int = 0
    handed: list[tuple[str, str, str]] = field(default_factory=list)

    def is_root(self) -> bool:
        return self.root

    def loader(self) -> str:
        return self.installed_loader

    def hand_off(self, loader: str, installed: str, language: str) -> int:
        self.handed.append((loader, installed, language))
        return self.result
