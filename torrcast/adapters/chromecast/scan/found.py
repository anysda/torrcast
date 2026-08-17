"""Итог поиска приёмников: что нашлось и о чём надо сказать вслух.

Собирает его :func:`find`, читает меню выбора приёмника."""

from __future__ import annotations

from dataclasses import dataclass, field

from torrcast.adapters.chromecast.scan.device import Device


@dataclass(slots=True)
class Found:
    """Итог поиска: приёмники и честные строки о том, чего мы не смотрели."""

    devices: list[Device] = field(default_factory=list)
    #: Пропущенные подсети и прочее, о чём человеку надо сказать вслух, а не умолчать.
    notes: list[str] = field(default_factory=list)
