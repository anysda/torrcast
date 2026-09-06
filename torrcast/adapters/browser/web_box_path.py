"""Называет путь почтового ящика вкладки: чем ``GET /api/web/box`` отвечает браузеру."""

from __future__ import annotations

from pathlib import Path
from typing import Final

#: Лежит рядом с сегментами показа (:func:`torrcast.usecases.playback.hls_root.hls_root`) -
#: тем же старым способом двум процессам сойтись файлом на общем диске, каким уже
#: сходятся показ и его CLI (:data:`torrcast.adapters.stream_pack.landed_path.LANDED_FILE`).
WEB_BOX_FILE: Final = "web_box.json"


def web_box_path(out: Path) -> Path:
    """Путь почтового ящика вкладки (:data:`WEB_BOX_FILE`)."""
    return out / WEB_BOX_FILE
