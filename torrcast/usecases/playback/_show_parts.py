"""Кодировщик тяжёлых кусков и прогрев одного показа на одной сетке.

Собирает их медиатракт (:func:`torrcast.usecases.playback._tract._tract`) и пересборка
сетки по концу картинки (:class:`torrcast.usecases.playback._ending._Ending`): у обоих
участников сетка обязана быть та же, что у упаковки.
"""

from __future__ import annotations

from pathlib import Path

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.config import Config
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.segment_container import MPEGTS, SegmentContainer
from torrcast.ports.recode.encoding import Encoding
from torrcast.ports.recode.spot_recoder import SpotRecoder
from torrcast.usecases.playback._recoder import _recoder
from torrcast.usecases.playback._warmer import _warmer
from torrcast.usecases.playback.following import Following
from torrcast.usecases.playback.media_grid import MediaGrid
from torrcast.usecases.warm.warmer import Warmer


def _show_parts(
    config: Config,
    source: str,
    audio: int,
    about: str,
    out: Path,
    grid: MediaGrid,
    whole: Encoding | None,
    start: float,
    video_mbit: float,
    *,
    follow: Following | None = None,
    profile: Profile = CAUTIOUS,
    video_mbit_estimated: bool = False,
    container: SegmentContainer = MPEGTS,
    voice: str = "",
    warm: bool = True,
) -> tuple[SpotRecoder | None, Warmer | None]:
    """Кодировщик тяжёлых кусков (нет при сплошном перекоде) и прогрев на сетке ``grid``.

    ``warm=False`` - прогрев у показа уже есть, и второй на новой сетке не собирается.
    """
    recoder = (
        None
        if whole is not None
        else _recoder(
            source,
            audio,
            grid,
            out / _state.RECODE_DIR,
            config,
            video_mbit=video_mbit,
            profile=profile,
            video_mbit_estimated=video_mbit_estimated,
            voice=voice,
        )
    )
    if not warm:
        return recoder, None
    warmer = _warmer(
        config,
        source,
        audio,
        grid,
        start,
        about,
        whole=whole,
        recoder=recoder,
        follow=follow,
        profile=profile,
        video_mbit=video_mbit,
        container=container,
        voice=voice,
    )
    return recoder, warmer
