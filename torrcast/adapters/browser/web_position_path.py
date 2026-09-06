"""Называет путь записи последней позиции, присланной вкладкой."""

from __future__ import annotations

from pathlib import Path
from typing import Final

#: Лежит рядом с почтовым ящиком (:data:`torrcast.adapters.browser.web_box_path.WEB_BOX_FILE`) -
#: тот же каталог сегментов показа, тот же общий диск.
WEB_POSITION_FILE: Final = "web_position.json"


def web_position_path(out: Path) -> Path:
    """Путь записи последней позиции вкладки (:data:`WEB_POSITION_FILE`)."""
    return out / WEB_POSITION_FILE
