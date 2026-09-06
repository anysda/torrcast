"""Читает задание вкладке; зовёт его страница на ``GET /api/web/box`` (:mod:`web.box`).

Второй же вкладке, спросившей то же самое, ящик отвечает тем же заданием - секунда
показа проверяется одним кодом что для приставки, что для второй вкладки (ТЗ §7.4):
запрет тут не заведён, и разбирать конфликт двух вкладок предстоит другому заходу.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from torrcast.adapters.browser._read_json import _read_json
from torrcast.adapters.browser.web_box_path import web_box_path


def read_web_box(out: Path) -> dict[str, Any]:
    """Задание вкладке, а показывать нечего - пустой словарь, а не ``None``.

    Пустой словарь - слово ``API``, а не внутренняя примета: страница отдаёт его в JSON
    как есть (:mod:`web.box`), и с той стороны розетки ``{}`` читается ровно как «сейчас
    ничего не играет».
    """
    return _read_json(web_box_path(out)) or {}
