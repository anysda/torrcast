"""Упаковка сдалась: переждать обрыв источника или честно похоронить показ.

Зовёт держатель показа (:func:`torrcast.usecases.revive_playback._hold._hold`) на том
круге опроса, где упаковка пожаловалась.
"""

from __future__ import annotations

from torrcast.domain.infra_error import InfraError
from torrcast.ports.clock import Clock
from torrcast.ports.journal import journal
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.feed_pack import Feed
from torrcast.usecases.source_blame import _asked


def _endure(
    feed: Feed,
    supply: StreamSource | None,
    clock: Clock,
    trouble: str,
    was_offline: bool,
) -> bool:
    """Пережить жалобу упаковки; возвращает новое «об аварии уже сказано».

    Возврат отсюда означает «круг опроса начинается заново»: показ не умер, он ждёт
    возврата источника. Ждать нечего - летит :class:`~torrcast.domain.infra_error.
    InfraError`, и это единственный выход отсюда, который не является ожиданием.
    """
    # 🔴 Упаковка сдалась - и вот теперь спрашиваем ИСТОЧНИК. Оборванные подряд
    # прогоны значат «показывать нечего» только при живом источнике; служба
    # раздач, которую перезапустили, рвёт вход так же, а ждать её три секунды.
    # Вопрос задаётся здесь, на краю показа, а не в горячем пути: раздача
    # сегментов не ждёт ни журнал, ни лишний запрос.
    why_source = _asked(supply)
    if why_source:
        feed.stall(why_source)  # показ не умирает, а ждёт возврата источника
        if not was_offline:  # говорим об аварии один раз, а не каждые две секунды
            was_offline = True
            journal().offline(why=why_source, asked=True)
            print(
                f"источник не читается ({why_source}) - жду его возврата, показ подниму сам",
                flush=True,
            )
        clock.sleep(2.0)
        return was_offline
    if supply is not None and supply.restored:
        # Источник вернулся ровно сейчас, и раздача у него снова с трекерами:
        # хоронить показ на этом месте было бы враньём - упаковка попробует ещё.
        feed.stall("")
        clock.sleep(2.0)
        return was_offline
    # Убитый сигналом ffmpeg ничего сказать не успевает - не выдумываем за него.
    raise InfraError(f"упаковка оборвалась: {trouble}")
