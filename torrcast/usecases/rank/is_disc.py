"""Признак образа диска в имени раздачи; зовут ворота отбора и порядок меню."""

from __future__ import annotations

from torrcast.domain.rank_settings import DISC_RE
from torrcast.domain.release import Release

_DISC_RE = DISC_RE


def is_disc(release: Release) -> bool:
    """Образ диска (DVD-Video, BDMV, ISO): цельного файла внутри нет — не дефолт."""
    return bool(_DISC_RE.search(release.raw_name))
