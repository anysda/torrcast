"""Называет путь отметки «эта серия последняя» - «Отмена» на плашке следующей серии."""

from __future__ import annotations

from pathlib import Path
from typing import Final

#: Лежит рядом с почтовым ящиком (:data:`torrcast.adapters.browser.web_box_path.WEB_BOX_FILE`):
#: отдельным файлом, а не полем ящика или позиции. Ящик снимает конец показа
#: (:meth:`torrcast.adapters.browser.browser_receiver.BrowserReceiver.stop`), а позицию
#: переписывает любая вкладка того же показа, и вторая вкладка, не видевшая «Отмены»,
#: стёрла бы её первым же своим докладом.
WEB_LAST_FILE: Final = "web_last.json"


def web_last_path(out: Path) -> Path:
    """Путь отметки последней серии (:data:`WEB_LAST_FILE`)."""
    return out / WEB_LAST_FILE
