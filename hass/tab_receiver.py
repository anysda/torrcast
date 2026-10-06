"""Показ идёт в самой вкладке: отличие вкладки от показа на ТВ по её ящику."""

from __future__ import annotations

from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.domain.config import Config
from torrcast.usecases.playback.hls_root import hls_root


def tab_receiver(config: Config) -> bool:
    """Показ идёт в самой вкладке, а не в отданном ей телевизоре.

    Голый ``url`` ящика вкладку от показа на ТВ не отличает, поле ``tv`` - отличает
    (:mod:`hass.remote_refused`).
    """
    box = read_web_box(hls_root(config.hls_dir))
    return bool(box.get("url")) and not box.get("tv", False)
