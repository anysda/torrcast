"""Полка после «готово» только усыхает: на ней нет ни одной новой плитки.

Холодный заход гасит счётчик страницы, когда обложки доехали, а приговоры «играет ли»
идут ещё 85-254 с (замер TC-1322). «Не играет» снимает плитку, и прежде её место тут же
занимала следующая картина очереди: на полке, которую страница уже назвала готовой,
появлялась новая плитка. Здесь запоминается состав полок в миг, когда счётчик погас, и
дальше публикуется только он, без снятых приговором.
"""

from __future__ import annotations

from dataclasses import dataclass

from torrcast.domain.json_value import JsonValue


def _keys(tiles: list[JsonValue]) -> list[str]:
    return [str(tile.get("key")) for tile in tiles if isinstance(tile, dict)]


@dataclass
class ReadyShelf:
    """Состав полок на миг «готово»; ``None`` - счётчик ещё горит, полка растёт."""

    keys: dict[str, set[str]] | None = None

    def watch(
        self, filling: bool, shown: dict[str, list[str]], done: dict[str, list[JsonValue]]
    ) -> bool:
        """Отдать признак счётчика; погас впервые - запомнить то, что видит страница."""
        if not filling and self.keys is None:
            seen = {**shown, **{shelf: _keys(tiles) for shelf, tiles in done.items()}}
            self.keys = {shelf: set(keys) for shelf, keys in seen.items()}
        return filling

    def keep(self, shelf: str, tiles: list[JsonValue]) -> list[JsonValue]:
        """Плитки полки, которые страница уже видела в «готово»; до него - все."""
        if self.keys is None:
            return tiles
        allowed = self.keys.get(shelf, set())
        return [tile for tile in tiles if isinstance(tile, dict) and tile.get("key") in allowed]


__all__ = ["ReadyShelf"]
