"""Подъём СВОЕГО погасшего показа: сессия мертва целиком, поднимаем с нуля.

Зовёт его воскрешение показа снаружи
(:class:`torrcast.usecases.revive_playback._revival._Revival`)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.chromecast.cast.past_deadly import _past_deadly
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.not_raised import NOT_RAISED
from torrcast.domain.why import why

if TYPE_CHECKING:
    from torrcast.adapters.chromecast.cast.receiver_talk import _Talk


def _replay(rcv: _Talk, at: float, paused: bool = False) -> float:
    """Поднять СВОЙ погасший показ с секунды ``at``; вернуть секунду, С КОТОРОЙ он пошёл.

    :data:`NOT_RAISED` - картинки нет: приёмник занят чужим показом, не взял LOAD или
    взял, но кадра так и не дал.

    ``paused=True`` - сессию возвращают на закладку БЕЗ начала показа (LOAD с
    ``autoplay=False``): паузу на ней ставил зритель, и снимает её тоже он
    (:mod:`torrcast.usecases.revive_playback._paused`). Готовность такого подъёма -
    слово ``PAUSED``, а не картинка
    (:meth:`torrcast.adapters.chromecast.cast.receiver_talk._Talk._settle`).

    🔴 Отказ отвечает отрицательной секундой, а не нулём, и это не педантизм. Ноль -
    законное место фильма: показ, умерший на 0:00, поднимают ровно с начала картины
    (:meth:`torrcast.usecases.revive_playback._revival._Revival.resurrect`), и такой подъём - удача,
    а не отказ. Пока оба ответа были нулём, различить их было нечем: удачный подъём с нуля уходил в
    ленту как «приёмник показ не взял» - при идущей картинке.

    🔴 Вернувшаяся секунда - НЕ та, о которой просили: показ, умирающий на одном
    куске, поднимают уже за ним (:meth:`_past_deadly`), и это до пятнадцати секунд
    фильма. Пока метод отвечал «да/нет», сказать о подъёме мог только тот, кто просил,
    - и говорил он про место, где показ как раз НЕ пошёл. Место подъёма знает тот,
    кто его выбрал, и отдаёт его наружу сам.

    Терпение приёмника конечно и меньше нашего. Замер 09-08-2026 на живом Samsung
    Q70D развёл два срока, которые раньше слипались в «~4 минуты»: медиасессия
    умирает через 23.5 с стоящей картинки (:attr:`torrcast.domain.profile.Profile.patience`),
    а приложение висит на экране ещё 301 с после её смерти
    (:attr:`torrcast.domain.profile.Profile.app_patience`). Пока сессия жива, приёмник сам
    перезабирает пропавший кусок по HTTP - два раза с шагом ~11 с; повторами LOAD это
    не было никогда, ``media_session_id`` при этом не меняется. Дальше повторять LOAD
    изнутри :meth:`position` уже некому - сессии нет, - и без этого метода обрыв
    длиннее приёмникова терпения означал бы поход человека к консоли.

    От :meth:`_reload` отличается тем, что чинит не показ, а его отсутствие: сессия
    мертва целиком, поэтому приложение поднимается с нуля (:meth:`_restart_app`), а
    позиция приходит снаружи - от того, кто её помнит (``at``), а не из ``current_time``
    мёртвой сессии, где лежит ноль.

    ⚠️ Воскрешаем **только своё** и только на свободном приёмнике (:meth:`_free`):
    пока нас не было, на том же ТВ могли начать смотреть что-то другое, и перебивать
    чужой показ нельзя - ни своим LOAD, ни ``quit_app`` перед ним.

    Исключения наружу не выпускаются: приёмника может не быть в сети вовсе, а это уже
    не авария показа - зовущий просто попробует ещё раз или честно погасит показ. Но
    причина не теряется вместе с исключением: она остаётся в :attr:`_Talk._refused`, и
    оттуда её называет лента (:meth:`ChromecastReceiver.refusal`).

    ⚠️ Место подъёма проходит через :meth:`_past_deadly`: показ, который умирает на
    одном и том же куске, поднимать в него же значит поднимать за следующей смертью.
    Счёт смертей по кускам сессию переживает нарочно - именно он и отличает
    невоспроизводимый кусок от невезучей минуты.
    """
    if not rcv._free():
        rcv._refused = phrase("chromecast_talk.refused_busy")
        return NOT_RAISED
    at = _past_deadly(rcv, at)
    # Сторож начинает счёт заново: сессия новая, и её подвисы к прошлой отношения не
    # имеют. ``_peak`` - это ``at``: именно с него приёмник и поедет.
    rcv._peak, rcv._at = at, at
    rcv._reloads, rcv._stall_hits = 0, 0
    rcv._stall_at, rcv._stall_since = -1.0, 0.0
    rcv._seen, rcv._seek_since, rcv._nudged_to = -1.0, 0.0, -1.0
    rcv._blind, rcv._gone = 0, False
    rcv._skip_from = -1.0  # о перешагнутом куске сказано выше, вторым голосом незачем
    try:
        rcv._restart_app()
        rcv._load(at, paused=paused)
        if rcv._settle(rcv.WAKE_TIMEOUT):
            rcv._refused = ""
            return at
    except Exception as exc:
        # 🔴 Проглотить исключение можно, потерять его причину - нет. Три исхода
        # «картинки не будет» стоят разных выводов: чужой показ на экране трогать НЕЛЬЗЯ
        # и ждать тут нечего, легшее соединение - это УПАЛ и лечится следующей попыткой
        # с чистым сокетом, а ушедший LOAD без кадра - это отказ самого приёмника. Пока
        # все три отвечали одним :data:`NOT_RAISED`, лента писала о них одну строку.
        rcv._refused = phrase("chromecast_talk.refused_crashed", reason=why(exc))
        return NOT_RAISED
    rcv._refused = phrase("chromecast_talk.refused_not_taken")
    return NOT_RAISED
