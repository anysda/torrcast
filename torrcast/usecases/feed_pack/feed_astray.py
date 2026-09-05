"""Заход встал не туда, куда обещала карта: снять доверие карте и зайти заново.

Зовут отсюда часы показа (:func:`torrcast.usecases.feed_pack.feed_sweep._sweep`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.feed_pack._state as _state
from torrcast.domain.hls_settings import SPLIT_SLACK
from torrcast.ports.journal.slot import journal

if TYPE_CHECKING:
    from collections.abc import Callable

    from torrcast.usecases.feed_pack.feed_state import _State

    _Lift = Callable[[_State, Callable[[int], None], int], None]


def _astray(state: _State, restart: Callable[[int], None], lift: _Lift) -> None:
    """Нарезанное разъехалось с манифестом - перезайти, больше не веря карте.

    🔴 Ради этого место захода и разрешено брать из карты даром. Прежде карте верили
    только после сверки с пробным прогоном - один прогон на файл, но ровно на пути к
    первой картинке (замер репы: 0.029 с на файле в tmpfs, 0.042 с по http на петле,
    против 1.6-10.9 мкс у самой карты). Сверка не отменена, а переехала с предсказания
    на факт: промах карты выходит наружу измеримо, потому что резы захода сегментный
    муксер отмеряет от ПЕРВОГО ПАКЕТА прогона, и вся нарезка уезжает ровно на промах.
    Замер репы (ровная сетка 10 с, 600 с плёнки): здоровый заход даёт ``drift``
    0.000 с на mkv и 0.006 с на mp4, а заход, которому соврали на 4.0 с, - ровно
    4.000 с. Порог поэтому берётся прежний, :data:`SPLIT_SLACK`: это тот же допуск, с
    которым сверялись карта и прогон, и он на порядок выше измеренного шума муксера.

    🔴 Молчания на этом месте быть не может, а ``drift`` молчит нулём: считается он по
    списку резов, пропуская первую строку (в ней ffmpeg пишет начало прогона нулём), и
    на списке короче двух строк отдаёт 0.0 - то есть «мерить нечем» выглядит как
    «разошлось на ноль». Поэтому мерка спрашивается только там, где счёт заведомо есть:
    край прогона ушёл дальше его же первого слота, а значит закрыт и второй кусок.

    Один раз на файл: сняв доверие карте, лента больше сюда не возвращается
    (:func:`torrcast.adapters.stream_pack.map_trusted.map_trusted`). Перезаход идёт уже
    пробным прогоном, и второй такой же разъезд означал бы не врущую карту, а больной
    источник - лечить его перезапусками бессмысленно, этим занят разбор обрыва.

    Куски своего же прогона от ``first`` до края сносятся: они лежат под верными именами
    с чужим содержимым, и запрос сегмента отдал бы их файлом, не спросив упаковку вовсе
    (:func:`torrcast.usecases.feed_pack.feed_segment._segment`). Оставить их значило бы
    вылечить только будущее прогона, а зрителю отдать ровно те куски, из-за которых
    перезаход и затеян.

    ``lift`` - сам перезаход, доводом: внутри него лежит пробный прогон до минуты по
    потолку (:data:`torrcast.domain.hls_wait.PILOT_TIMEOUT`), и часам показа ждать его
    нельзя - они обязаны вернуться через свои две секунды.
    """
    packer = state.packer
    if packer is None or state.fatal or packer.stopped or packer.halted:
        return
    # Перекодирующий заход карту не спрашивает вовсе: опорные кадры он ставит САМ и ровно
    # на границы сетки (:func:`ffmpeg_pack_command`), и место захода ему не меряют ничем.
    if state.encode is not None or not _state.map_trusted(state.source):
        return
    if packer.edge <= packer.first:
        return
    drift = packer.drift(state.grid)
    if drift <= SPLIT_SLACK:
        return
    if not state.lock.acquire(blocking=False):
        return
    handed = False
    try:
        # Под замком спрашивается ещё раз: решение это одно на файл, а сюда приходят и
        # часы показа, и запрос сегмента.
        if not _state.map_trusted(state.source):
            return
        _state.map_lied(state.source)
        journal().mark(
            "нарезка разошлась с манифестом",
            слот=packer.first,
            край=packer.edge,
            расхождение=round(drift, 3),
        )
        for slot in range(packer.first, packer.edge + 1):
            (state.out / state.piece_name(slot)).unlink(missing_ok=True)
        state.restarted = _state.clock_port.monotonic()
        # Замок отсюда уносит перезаход и отпускает его сам - тем же порядком, что и
        # подъём оборванного прогона.
        _state.spawn(lambda: lift(state, restart, packer.first))
        handed = True
    finally:
        if not handed:
            state.lock.release()
