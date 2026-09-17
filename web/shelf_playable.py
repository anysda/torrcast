"""Приговор «плитка полки запускается»: тот же отбор, что и карточка, но фоном.

Владелец пожаловался дословно: карточки вроде «Sarpanch» стоят на главной и просто не
запускаются. Единственный честный признак - тот же, каким карточка решает, играть ли
«Играть» (:mod:`web.card`, ``voices_pending == false and release == null``): картина
годна, только если фоновый отбор дочитал раздачу и нашёл в ней дорожку
(:class:`web.voice_lookup.VoiceLookup`). Дешёвых заменителей нет - девять проверено и
отброшено разведкой TC-1343 контрпримерами.

Цену платит часовая пересборка полок (:mod:`web.shelves_cache`), а не открытие
страницы: здесь свой, отдельный от карточки прогрев (:class:`web.card_warm.CardWarm`) -
общий с карточкой стенд означал бы, что сборка полки на ходу отбирает раздачу у
зрителя, который в этот момент держит открытую карточку. И свой ``spawn``, синхронный:
пересборка уже в фоновом потоке, ждать там можно, а `VoiceLookup.of` со стандартным
демоном отдал бы «ещё считается» вместо готового приговора.

Вердикт запоминается по картине ПЛЮС номеру правила отбора (:mod:`web.built_by_rule`):
не часами, как у самой карточки (:data:`web.episode_lookup.RETRY` - 60 с, для часового
цикла это ничего не экономит), а до следующей смены правила. Повторная пересборка тех
же плиток вообще не трогает стенд.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.domain.config import Config
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.usecases.select.plan import Plan
from web.built_by_rule import RULE
from web.card_warm import CardWarm
from web.heard import Heard
from web.voice_lookup import VoiceLookup
from web.warm_wiring import WARM

#: Круг раздач по запросу плитки; в бою - :meth:`web.warm_cache.WarmCache.take`.
Circle = Callable[[str], list[Plan]]
#: Отбор дорожек; в бою - :meth:`web.voice_lookup.VoiceLookup.of`.
Voices = Callable[[Plan, str, Config], tuple["Heard | None", bool]]
#: Порт наружу: запрос и ключ плитки, приговор - играет она или нет.
PlayableOf = Callable[[str, str, Config], bool]


def _now(job: Callable[[], None]) -> None:
    """Фон пересборки уже свой поток: приговор ждём тут же, а не вторым демоном."""
    job()


@dataclass
class ShelfPlayable:
    """Приговор плитки с памятью на процесс, отдельной от отбора живой карточки."""

    circle: Circle
    voices: Voices
    _verdicts: dict[str, tuple[int, bool]] = field(default_factory=dict)

    def of(self, query: str, key: str, config: Config) -> bool:
        """Играет ли плитка; готовый вердикт того же правила не перепрашивается."""
        cached = self._verdicts.get(key)
        if cached is not None and cached[0] == RULE:
            return cached[1]
        playable = self._resolve(query, key, config)
        self._verdicts[key] = (RULE, playable)
        return playable

    def _resolve(self, query: str, key: str, config: Config) -> bool:
        try:
            plans = self.circle(query)
        except TorrcastError:
            return False
        plan = next((one for one in plans if one.picture.key == key), None)
        if plan is None or not plan.ranked:
            return False
        heard, _pending = self.voices(plan, query, config)
        return heard is not None


#: Стенд отбора плиток полки: свой, не общий с открытой карточкой (:mod:`web.card`).
_WARM: Final = CardWarm()
#: Отбор плитки полки: та же логика, что у карточки (:mod:`web.voice_lookup`), но
#: синхронная и на своём стенде.
_VOICES: Final = VoiceLookup(engines=TorrServer, warms=_WARM, spawn=_now)
#: Боевой приговор: круг тот же, что у карточки и полки (:data:`web.warm_wiring.WARM`).
PLAYABLE: Final = ShelfPlayable(circle=WARM.take, voices=_VOICES.of)


__all__ = ["PLAYABLE", "PlayableOf", "ShelfPlayable"]
