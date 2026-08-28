"""Публичный фасад профилей приёмника."""

from typing import Final

from torrcast.domain.android_tv_profile import ANDROID_TV
from torrcast.domain.receiver_profile import (
    CAUTIOUS,
    COPY,
    RECODE,
    REFUSE,
    ReceiverProfile,
    Verdict,
)

__all__ = [
    "ANDROID_TV",
    "CAUTIOUS",
    "COPY",
    "PROFILES",
    "RECODE",
    "REFUSE",
    "Profile",
    "Verdict",
]

Profile = ReceiverProfile
PROFILES: Final = {profile.key: profile for profile in (CAUTIOUS, ANDROID_TV)}
