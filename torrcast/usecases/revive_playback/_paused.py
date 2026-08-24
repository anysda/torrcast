"""Пауза зрителя: гасим упаковку по сроку, а потерю сессии переживаем на закладке.

Зовёт её держатель показа (:func:`torrcast.usecases.revive_playback._hold._hold`), и только он.
"""

from __future__ import annotations

from torrcast.domain.profile import Profile
from torrcast.domain.start_settings import PAUSE_LIMIT, PAUSE_SECONDS
from torrcast.ports.clock import Clock
from torrcast.ports.receiver import Receiver
from torrcast.usecases.choice._ctl import _Revivable
from torrcast.usecases.feed_pack.feed import Feed
from torrcast.usecases.rank._hms import _hms
from torrcast.usecases.revive_playback._screen_state import _Screen


def _pause(
    screen: _Screen,
    receiver: Receiver,
    feed: Feed,
    profile: Profile,
    clock: Clock,
    alive: bool,
    pos: float,
) -> bool:
    """``True`` - ждём зрителя дальше; ``False`` - пауза длиной с вечер, показ окончен.

    ``alive`` - приёмник держит сессию и называет её ``PAUSED``. ``False`` - сессия
    потеряна (``UNKNOWN``/``IDLE`` с нулём): слово приёмника больше не различает паузу
    зрителя и смерть показа, а различие тут одно - паузу ставил ЗРИТЕЛЬ, и показ об
    этом помнит (:attr:`_Screen.paused`). Поднимать такой показ в ``PLAYING`` значит
    снять чужую паузу молча - брак того же класса, что чужой фильм под знакомым именем.
    Поэтому сессию возвращают на закладку БЕЗ начала показа (LOAD с ``autoplay=False``):
    зритель придёт и снимет паузу с пульта сам. Замер 24-08-2026, живой сеанс на
    Samsung Q70D: показ, поднятый лестницей воскрешения поверх зрительской паузы,
    играл без спроса, пока зритель ходил в магазин.

    Срок паузы (:data:`PAUSE_LIMIT`) тикает от её начала и потерей сессии не
    сбрасывается: пауза длиной с вечер по-прежнему кончает сеанс.

    ``pos`` - закладка: последний кадр, который зритель видел, а кадра не было - место,
    с которого показ заводили. У мёртвой сессии позиции нет вовсе, там ноль.
    """
    screen.paused = screen.paused or clock.monotonic()
    if clock.monotonic() - screen.paused > PAUSE_LIMIT:
        return False  # пауза длиной с вечер - показ окончен, юнит гасим
    if alive:
        screen.restore_since, screen.restore_at = 0.0, 0.0
        if clock.monotonic() - screen.paused > PAUSE_SECONDS and not feed.halted():
            print("пауза на пульте - упаковку гашу", flush=True)
            feed.halt()  # вернутся к показу - раздача сама начнёт паковать заново
        return True
    _restore(screen, receiver, profile, clock, pos)
    return True


def _restore(
    screen: _Screen, receiver: Receiver, profile: Profile, clock: Clock, pos: float
) -> None:
    """Вернуть потерянную на паузе сессию на закладку, НЕ начиная показ.

    Попытки разнесены как у лестницы воскрешения и по той же мере: приёмник, бросивший
    показ, берёт LOAD не сразу (:attr:`Profile.revive_drop` до первой, дальше -
    :attr:`Profile.revive_pause`). Потолка попыткам нет нарочно: их срок -
    :data:`PAUSE_LIMIT`, который тикает от начала паузы. Чужой показ на приёмнике при
    этом неприкосновенен - его проверяет сам подъём
    (:meth:`torrcast.adapters.chromecast.cast.chromecast_receiver.ChromecastReceiver.replay`).
    """
    if not isinstance(receiver, _Revivable):
        return  # возвращать сессию нечем - просто ждём зрителя до срока паузы
    now = clock.monotonic()
    if not screen.restore_since:
        screen.restore_since = now
        print(
            f"сессию на паузе приёмник потерял - возвращаю показ на {_hms(pos)}; "
            "сам он не начнётся",
            flush=True,
        )
    interval = profile.revive_pause if screen.restore_at else profile.revive_drop
    if now - (screen.restore_at or screen.restore_since) < interval:
        return
    screen.restore_at = now
    back = receiver.replay(pos, paused=True)
    if back >= 0:
        # Место называет приёмник, а не просьба: подъём вправе перешагнуть кусок.
        print(f"показ вернул на {_hms(back)} и стоит на паузе - жду зрителя", flush=True)
        screen.restore_since, screen.restore_at = 0.0, 0.0
