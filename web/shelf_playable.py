"""Приговор «плитка полки запускается»: тот же отбор, что и карточка, но фоном.

Владелец пожаловался дословно: карточки вроде «Sarpanch» стоят на главной и просто не
запускаются. Единственный честный признак - тот же, каким карточка решает, играть ли
«Играть» (:mod:`web.card`, ``voices_pending == false and release == null``): картина
годна, только если фоновый отбор дочитал раздачу и нашёл в ней дорожку
(:class:`web.voice_lookup.VoiceLookup`). Дешёвых заменителей нет - девять проверено и
отброшено разведкой TC-1343 контрпримерами.

Приговор ТРЁХсоставный, не булев: **играет**, **не играет**, **не знаю**. Булевым
признаком его записал первый заход, и это было неверно - отказ сети или мёртвый стенд
неотличим снаружи от честного «дорожки нет», а с булевым приговором оба читаются как
«не играет» и плитку выбрасывают за чужую поломку. «Не знаю» плитку не трогает - она
остаётся на полке, как была бы без отбора, - и не запоминается: следующий круг спросит
снова. Разбор источников «не знаю»:

- :class:`torrcast.domain.torrcast_error.TorrcastError` от круга (:attr:`circle`)
  - молчание индексера или каталога;
- ключа плитки нет среди планов круга - круг мог не дойти именно до этой картины;
- ``voices_pending == true`` - отбор дорожек ещё не дочитал раздачу;
- стенд TorrServer недоступен (:func:`_alive`) - проверяется ДО начала отбора, отдельно
  от круга и от дорожек: и круг (поиск по индексерам), и запись «дорожек нет» внутри
  :meth:`web.voice_lookup.VoiceLookup._build` сами гасят инфраструктурный отказ молча
  (``except TorrcastError: prep = None``) и пишут его как честное «дорожек нет» -
  дерево `voice_lookup.py` тут не трогается (общий с карточкой файл, не наш периметр),
  и различить изнутри эти два случая нечем. Дешёвая проверка стенда самим ``/echo``
  ДО дорогого разбора - единственный честный способ не приписать поломку стенда
  картине.

``not plan.ranked`` - отдельный случай, и он «не играет», а не «не знаю»: план,
который вернул круг, уже готов целиком (круг не отдаёт недостроенные планы - его
раздачи и рейтинг посчитаны на месте, см. :meth:`torrcast.usecases.select.plan.Plan.
candidates`), так что пустой список - это честный факт «раздач под картину не
нашлось», а не «ещё считается».

Цену платит часовая пересборка полок (:mod:`web.shelves_cache`), а не открытие
страницы: здесь свой, отдельный от карточки прогрев (:class:`web.card_warm.CardWarm`) -
общий с карточкой стенд означал бы, что сборка полки на ходу отбирает раздачу у
зрителя, который в этот момент держит открытую карточку. И свой ``spawn``, синхронный:
пересборка уже в фоновом потоке, ждать там можно, а `VoiceLookup.of` со стандартным
демоном отдал бы «ещё считается» вместо готового приговора.

Вердикт запоминается по картине ПЛЮС номеру правила отбора (:mod:`web.built_by_rule`):
не часами, как у самой карточки (:data:`web.episode_lookup.RETRY` - 60 с, для часового
цикла это ничего не экономит), а до следующей смены правила - и на диске
(:class:`web.verdict_disk.VerdictDisk`), тем же приёмом, каким круг переживает рестарт
(:class:`web.circle_disk.CircleDisk`): рестарт службы не вправе обнулять память, за
которую уже заплачено секундами TorrServer. Повторная пересборка тех же плиток вообще
не трогает стенд - но только для готовых приговоров: «не знаю» памяти не имеет никогда,
ни в процессе, ни на диске.
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
from web.verdict_disk import VerdictDisk
from web.voice_lookup import VoiceLookup
from web.warm_wiring import WARM

#: Круг раздач по запросу плитки; в бою - :meth:`web.warm_cache.WarmCache.take`.
Circle = Callable[[str], list[Plan]]
#: Отбор дорожек; в бою - :meth:`web.voice_lookup.VoiceLookup.of`.
Voices = Callable[[Plan, str, Config], tuple["Heard | None", bool]]
#: Жив ли стенд раздач ДО того, как его спрашивать; в бою - :meth:`TorrServer.alive`.
Alive = Callable[[Config], bool]
#: Приговор: ``True`` - играет, ``False`` - честно не играет, ``None`` - не знаем.
Verdict = bool | None
#: Порт наружу: запрос и ключ плитки, приговор - играет ли, не играет ли, или не знаем.
PlayableOf = Callable[[str, str, Config], Verdict]


def _now(job: Callable[[], None]) -> None:
    """Фон пересборки уже свой поток: приговор ждём тут же, а не вторым демоном."""
    job()


def _alive(config: Config) -> bool:
    """Дёшево спросить стенд ``/echo`` до дорогого разбора раздачи (:data:`Alive`)."""
    return TorrServer(config.torrserver_url).alive()


@dataclass
class ShelfPlayable:
    """Приговор плитки с памятью на процесс, отдельной от отбора живой карточки."""

    circle: Circle
    voices: Voices
    alive: Alive = _alive
    #: Диск, переживающий рестарт (:class:`web.verdict_disk.VerdictDisk`); ``None`` в
    #: тестах - память тогда живёт ровно на процесс, как и раньше.
    disk: VerdictDisk | None = None
    _verdicts: dict[str, tuple[int, bool]] = field(default_factory=dict)

    def of(self, query: str, key: str, config: Config) -> Verdict:
        """Приговор плитки; готовый вердикт того же правила не перепрашивается.

        Память двухслойная: сперва процесс (дешевле), затем диск (переживает рестарт) -
        и только если оба молчат, отбор платит секундами TorrServer заново. ``None``
        («не знаю») наружу тоже отдаётся честно - место действия оставляет принять
        :func:`web.shelf_tiles._covered`, а не эта функция, - и ни в память процесса,
        ни на диск никогда не пишется.
        """
        cached = self._verdicts.get(key)
        if cached is not None and cached[0] == RULE:
            return cached[1]
        if self.disk is not None:
            stored = self.disk.get(key, RULE)
            if stored is not None:
                self._verdicts[key] = (RULE, stored)
                return stored
        verdict = self._resolve(query, key, config)
        if verdict is None:
            return None
        self._verdicts[key] = (RULE, verdict)
        if self.disk is not None:
            self.disk.keep(key, RULE, verdict)
        return verdict

    def _resolve(self, query: str, key: str, config: Config) -> Verdict:
        if not self.alive(config):
            return None
        try:
            plans = self.circle(query)
        except TorrcastError:
            return None
        plan = next((one for one in plans if one.picture.key == key), None)
        if plan is None:
            return None
        if not plan.ranked:
            return False
        heard, pending = self.voices(plan, query, config)
        if pending:
            return None
        return heard is not None


#: Стенд отбора плиток полки: свой, не общий с открытой карточкой (:mod:`web.card`).
_WARM: Final = CardWarm()
#: Отбор плитки полки: та же логика, что у карточки (:mod:`web.voice_lookup`), но
#: синхронная и на своём стенде.
_VOICES: Final = VoiceLookup(engines=TorrServer, warms=_WARM, spawn=_now)
#: Боевой приговор: круг тот же, что у карточки и полки (:data:`web.warm_wiring.WARM`),
#: память - на диске, переживает рестарт (:class:`web.verdict_disk.VerdictDisk`).
PLAYABLE: Final = ShelfPlayable(circle=WARM.take, voices=_VOICES.of, disk=VerdictDisk())


__all__ = ["PLAYABLE", "PlayableOf", "ShelfPlayable", "Verdict"]
