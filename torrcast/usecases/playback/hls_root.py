"""Каталог сегментов показа: явное умолчание уступает переопределению окружением.

Зовёт запуск показа (:mod:`torrcast.usecases.playback._launch`), там, где боевой
каталог трогают синхронно, а не через :func:`torrcast.adapters.stream_pack.hls_dir.hls_dir`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from torrcast.domain._config_hls import DEFAULT_HLS_DIR
from torrcast.domain.instance_slug import instance_slug

#: ``TORRCAST_HLS=<каталог>`` - куда смотреть вместо БОЕВОГО умолчания
#: (:data:`torrcast.domain._config_hls.DEFAULT_HLS_DIR`). Того же рода переопределение,
#: что и :data:`torrcast.usecases.warm.settings.WARM_ENV`: тестовый прогон не имеет
#: права трогать каталог живого показа (TC-891).
HLS_ENV: Final = "TORRCAST_HLS"


def hls_root(configured: str) -> Path:
    """Каталог сегментов показа.

    Явно заданный каталог (свой ``tmp_path`` юнит-теста, настроенное человеком место)
    сильнее и возвращается как есть. Подмена срабатывает только там, где настройка
    осталась НЕИЗМЕНЁННЫМ умолчанием - то есть ровно там, где иначе досталась бы боевая
    ``/dev/shm/torrcast``. Без подмены окружением небоевой экземпляр получает каталог со
    своей меткой (:func:`torrcast.domain.instance_slug.instance_slug`): иначе все полосы узла
    паковали бы в один каталог и гасили друг друга (TC-1137).
    """
    if configured != DEFAULT_HLS_DIR:
        return Path(configured)
    override = os.environ.get(HLS_ENV)
    if override:
        return Path(override)
    slug = instance_slug()
    return Path(f"{configured}-{slug}") if slug else Path(configured)
