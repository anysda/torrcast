"""Рабочий каталог головы на полке прогрева: пока он есть, голову этого места кладут.

Кладёт голову :func:`torrcast.usecases.warm.lay_head.lay_head` из процесса страницы, а
ждёт её показ из своего (:mod:`torrcast.usecases.feed_pack.feed_heading`): общего у них
только полка, и знак захода - каталог на ней с номером места в имени.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def head_work(shelf: Path, slot: int) -> Path:
    """Каталог захода головы места ``slot`` на полке ``shelf``.

    Имя не подходит под ``v*``: куском его не считает ни полка, ни показ.
    """
    return shelf / f"head-{slot}"


__all__ = ["head_work"]
