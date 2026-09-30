"""Публичный фасад профилей приёмника."""

from typing import Final

from torrcast.domain.android_tv_profile import ANDROID_TV
from torrcast.domain.browser_profile import BROWSER
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
    "BROWSER",
    "CAUTIOUS",
    "COPY",
    "PROFILES",
    "RECODE",
    "REFUSE",
    "Profile",
    "Verdict",
]

Profile = ReceiverProfile
#: Профили, которые можно назвать руками (``receiver_profile``). :data:`BROWSER` сюда не входит:
#: его выдаёт только замеренная вкладка (:func:`torrcast.domain.for_tab.for_tab`), а названный
#: руками на машине с Chromecast он отдал бы телевизору куски, снятые под браузер.
PROFILES: Final = {profile.key: profile for profile in (CAUTIOUS, ANDROID_TV)}
