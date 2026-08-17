"""Каталог, в который кладётся прогретое.

Зовут показ (:mod:`torrcast.usecases.playback`) и сторож диска, когда собирают хранилище.
"""

from __future__ import annotations

import os
from pathlib import Path

from torrcast.domain.warm_settings import WARM_DIR
from torrcast.usecases.warm.settings import WARM_ENV


def warm_root(configured: str = WARM_DIR) -> Path:
    """Каталог прогретого с учётом :data:`WARM_ENV`."""
    return Path(os.environ.get(WARM_ENV) or configured or WARM_DIR)
