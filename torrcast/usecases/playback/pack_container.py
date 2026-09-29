"""Во что пакуются куски показа - одним правилом для показа и прогрева."""

from __future__ import annotations

from torrcast.domain.profile import Profile
from torrcast.domain.segment_container import MPEGTS, SegmentContainer
from torrcast.ports.recode.encoding import Encoding


def pack_container(profile: Profile, whole: Encoding | None) -> SegmentContainer:
    """Во что пакуются куски: сплошной перекод идёт в MPEG-TS, остальное - в контейнер
    приёмника. Контейнер входит в ключ полки (:func:`torrcast.usecases.warm.warm_key`), и
    прогрев, решивший его по-своему, грел бы мимо показа."""
    return profile.segment_container if whole is None else MPEGTS
