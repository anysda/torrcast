"""Приглушить косметическую жалобу pychromecast на порт 8443.

Зовут её все, кто поднимает pychromecast: показ, поиск приёмников и опрос имени."""

from __future__ import annotations

import logging

from torrcast.adapters.chromecast.cast.cosmetic import _DIAL_LOGGER, _Cosmetic


def hush_cosmetic_noise() -> None:
    """Повесить :class:`_Cosmetic` на логгер pychromecast; звать можно сколько угодно.

    Зовётся отовсюду, где поднимается pychromecast: и перед показом
    (:meth:`ChromecastReceiver._device`), и при поиске приёмников (:mod:`torrcast.scan`).
    """
    logger = logging.getLogger(_DIAL_LOGGER)
    if not any(isinstance(one, _Cosmetic) for one in logger.filters):
        logger.addFilter(_Cosmetic())
