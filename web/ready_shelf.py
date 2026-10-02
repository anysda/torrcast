"""Полка после «готово» только усыхает: ни новой плитки, ни новой обложки на старой.

Холодный заход гасит счётчик страницы, когда обложки доехали, а приговоры «играет ли»
идут ещё 85-254 с (замер TC-1322). «Не играет» снимает плитку, и прежде её место тут же
занимала следующая картина очереди; а лента, недосчитавшая индексер, добиралась новыми
заходами и приносила полке новые плитки уже после «готово». Здесь в миг, когда счётчик
погас, запоминается опубликованный состав полок, и до конца пересборки (все её заходы
делят один :class:`ReadyShelf`) публикуется только он, без снятых приговором «не играет».
Полку, которую приговоры опустошили, держать незачем: заморозка снимается, и пустая полка
добирается, как до «готово».
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from torrcast.domain.json_value import JsonValue
from web.cold import SHELVES


def _key(tile: JsonValue) -> str:
    return str(tile.get("key")) if isinstance(tile, dict) else ""


@dataclass
class ReadyShelf:
    """Состав полок на миг «готово»; ``None`` - счётчик ещё горит, полка растёт."""

    tiles: dict[str, list[JsonValue]] | None = None
    seen: dict[str, list[JsonValue]] = field(default_factory=dict)
    lit: bool = False  # the counter burned: a warm rebuild has no «ready» to keep

    def saw(self, shelf: str, tiles: list[JsonValue]) -> None:
        """Запомнить то, что ушло на страницу: застывает именно оно."""
        self.seen[shelf] = tiles

    def watch(self, filling: bool) -> bool:
        """Признак счётчика: погас при обеих непустых полках - застыл и больше не горит."""
        self.lit = self.lit or filling
        full = all(self.seen.get(shelf) for shelf in SHELVES)
        if self.tiles is None and self.lit and not filling and full:
            self.tiles = {shelf: list(tiles) for shelf, tiles in self.seen.items()}
        return filling and self.tiles is None

    def keep(
        self, shelf: str, tiles: list[JsonValue], verdicts: Mapping[str, bool | None]
    ) -> list[JsonValue]:
        """До «готово» - ``tiles``; после - застывшая полка без приговорённых «не играет»."""
        if self.tiles is None:
            return tiles
        kept = [tile for tile in self.tiles.get(shelf, []) if verdicts.get(_key(tile)) is not False]
        if not kept:  # condemned to empty: no «ready» left to keep, a fuller attempt may follow
            self.tiles = None
            return kept
        self.tiles[shelf] = kept
        return kept


__all__ = ["ReadyShelf"]
