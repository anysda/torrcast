"""Сетка и сплошной перекод серии по её записи: один перевод для показа, прогрева и головы."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.ports.recode.encoding import Encoding
from torrcast.usecases.playback.layout import layout
from torrcast.usecases.playback.media_grid import MediaGrid


def entry_layout(
    config: Config,
    source: str,
    entry: Entry,
    profile: Profile = CAUTIOUS,
    file_size: int = 0,
    say: Callable[[str], None] | None = None,
) -> tuple[MediaGrid, Encoding | None]:
    """Сетка и сплошной перекод серии по её записи - единственный перевод записи в
    :func:`layout`.

    🔴 Показ и прогрев следующей серии обязаны прийти сюда с ОДНОЙ записью, собранной
    одним правилом (:func:`torrcast.domain.episode_passport.episode_passport`), а не
    каждый со своим пересказом паспорта: пока прогрев звал :func:`layout` с голым весом
    ffprobe, у HEVC без веса в паспорте прогретое ложилось под чужим ключом.
    """
    return layout(
        config,
        source,
        entry.dur,
        entry.codec,
        max(0.0, entry.vbps),
        say=say,
        depth=entry.depth,
        profile=profile,
        frame=entry.frame,
        hdr=entry.hdr,
        file_size=file_size,
    )
