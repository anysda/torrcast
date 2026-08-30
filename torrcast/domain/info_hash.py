"""Инфохэш раздачи - устойчивое её имя между двумя поисками."""

from __future__ import annotations

from torrcast.domain.magnet_hash import magnet_hash
from torrcast.domain.release import Release


def info_hash(release: Release) -> str:
    """Инфохэш из магнита - устойчивое имя раздачи между двумя поисками."""
    return magnet_hash(release.magnet)
