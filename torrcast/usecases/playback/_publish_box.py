"""Кладёт вкладке ящик за приёмник, который сам о себе так не расскажет.

Зовёт её :func:`torrcast.usecases.playback._play._play`, и только она.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.config import Config
from torrcast.domain.profile import Profile
from torrcast.domain.segment_container import MPEGTS
from torrcast.ports.receiver import Receiver


def _publish_box(
    config: Config,
    receiver: Receiver,
    out: Path,
    url: str,
    about: str,
    start: float,
    profile: Profile,
) -> None:
    """Положить в ящик задание за ЛЮБОЙ приёмник, кроме вкладки: она кладёт своё сама.

    🔴 TC-1224. Ящик (:func:`torrcast.adapters.browser.write_web_box.write_web_box`) до
    сих пор клала только сама вкладка, из своего же приёмника
    (:meth:`torrcast.adapters.browser.browser_receiver.BrowserReceiver.play`). Показ,
    поднятый прямо на ТВ, вкладку об этом не извещал никак - открыть карточку той же
    картины и подключиться было нечем: ящик стоял пустым весь показ. ``tv=True``
    говорит подключившейся вкладке заглушить себя сразу же (:mod:`web.box`), а не ждать
    отдельного слова каста, которого при прямом показе на ТВ не будет вовсе.
    """
    if config.receiver == "browser":
        return
    _state.publish_box(
        out,
        url,
        about,
        start,
        uuid.uuid4().hex,
        profile.key,
        str(getattr(receiver, "segment_container", MPEGTS)),
        True,
    )
