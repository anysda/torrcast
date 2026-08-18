"""Кто виноват в темноте и вернулась ли сеть - два вопроса лестницы подъёма.

Зовёт их сама лестница (:class:`torrcast.usecases.revive_playback._revival._Revival`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.ports.journal import journal
from torrcast.usecases.feed_pack import Feed
from torrcast.usecases.source_blame import _asked, _blamed
from torrcast.usecases.warm import Warmer

if TYPE_CHECKING:
    from torrcast.usecases.revive_playback._revival_state import _RevivalState


def _why(state: _RevivalState, feed: Feed) -> str:
    """Из-за чего погас показ. Прежде чем винить приёмник, спрашиваем ИСТОЧНИК.

    Порядок именно такой. Приёмник гаснет молча и одинаково - и когда он сам исчерпал
    терпение, и когда ему нечего показывать, потому что источника не стало. Свои
    признаки показа тут не помощники: обрыв службы раздач на три секунды не взводит ни
    счёт оборванных прогонов, ни часы молчания (:data:`torrcast.domain.hls_settings.MUTE_SECONDS`), и
    :attr:`Feed.offline` остаётся пустым. Вопрос источнику стоит двух запросов и
    задаётся ровно один раз - в тот момент, когда показ уже признан погасшим.

    Причина возвращается одной строкой, и она же уезжает и в след, и человеку на
    экран: двух разных мнений о том, что случилось, быть не должно.
    """
    why_source = _blamed(state.supply, state.clock)
    if why_source:
        state.blamed = True
        if why_source != str(feed.offline):  # об одной аварии след пишет один раз
            journal().offline(why=why_source, asked=True)
        # Показ узнаёт причину от нас: дальше по ней живёт и упаковка (пробовать
        # реже, не умирать), и сам :class:`_Revival` (:meth:`_may`).
        feed.offline = why_source
        return why_source
    if feed.offline:
        return str(feed.offline)
    # Источник спрошен и здоров, упаковка на обрыв не жаловалась - винить некого,
    # кроме приёмника. Возврата в такой темноте ждут от него же (:meth:`resurrect`).
    state.dropped = True
    return "приёмник бросил показ"


def _may(state: _RevivalState, feed: Feed, warmer: Warmer | None, pos: float) -> bool:
    """Вернулась ли сеть - по факту, а не по часам.

    Прогретое сильнее любого признака сети: лежащий на диске фильм смотрится и без
    интернета вовсе, и ждать его возврата было бы враньём.

    Когда погасли из-за источника, спрашиваем ровно его же: :attr:`Feed.offline` в
    этом случае снимает только выложенный кусок, а выкладывать некому - упаковка ждёт
    запроса приёмника, а приёмник тёмен. Заодно это единственное место, где раздача
    возвращается магнитом: служба ответила - значит, самое время вернуть ей трекеры,
    и сделать это надо ДО того, как приёмник попросит поток по голому хэшу.
    """
    if warmer is not None:
        if warmer.done:
            return True
        if warmer.warmed > state.warmed:
            return True
    if state.blamed and state.supply is not None:
        if _asked(state.supply):
            return False  # источник всё ещё лежит - жечь терпение приёмника незачем
        feed.offline = ""
        state.why = "источник вернулся - жду готовности потока"
        # Ответ службы доказывает возврат источника, но не готовность потока. После
        # повторного добавления раздача ещё собирает метаданные и пиров; LOAD имеет
        # смысл лишь тогда, когда упаковка уже отдала кусок у сохранённой позиции.
        return feed.front(pos) > pos
    return not feed.offline
