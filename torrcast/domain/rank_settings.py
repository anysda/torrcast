"""Пороговые значения чистых правил ранжирования релизов."""

import re
from typing import Final

ALIVE_SEEDERS: Final = 5
EXTRAS_MBIT: Final = 2.0
FULL_HD_LIVENESS: Final = 0.25
FULL_HEIGHT: Final = 1080
GATE_LIVENESS: Final = 0.25
HD_HEIGHT: Final = 720
HONEST_RATIO: Final = 0.9
PEER_GRACE: Final = 6.0
RECODE_HEIGHT: Final = 1080
SD_BITRATE: Final = 4.0
SEASON_EPISODES: Final = 6
SOUND_LIVENESS: Final = 0.10
STEP_GRACE: Final = 10.0
TABLE_LIMIT: Final = 12
VOICE_MENU: Final = 0

DISC_RE: Final = re.compile(
    r"\b(?:video_?ts|bdmv|dvd[- ]?video|dvd[59]|iso|blu-?ray\s*(?:disc|cee)|avc\+?\s*iso)\b",
    re.IGNORECASE,
)
