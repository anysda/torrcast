"""Всё, что живой приёмник про себя знает: адрес, профиль, часы и ход показа.

Наследует их :class:`ChromecastReceiver`, и только он; занятия приёмника берут это
состояние параметром."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from torrcast.adapters.chromecast.cast.receiver_settings import _Settings
from torrcast.adapters.system_clock import SystemClock
from torrcast.domain.infra_error import InfraError
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.ports.clock import Clock


class _State(_Settings):
    """Поля живого приёмника: настройки показа и ход текущей сессии."""

    def __init__(
        self, address: str, profile: Profile = CAUTIOUS, clock: Clock | None = None
    ) -> None:
        if not address:
            raise InfraError("адрес ТВ не задан: cast --tv - найдёт телевизоры в сети")
        self.address = address
        #: Профиль этого приёмника: его терпение, его повторы LOAD, его сторож нуджей.
        #: Умолчание осторожное - показ без выбранного профиля ведёт себя как раньше.
        self.profile = profile
        #: Чем меряются выдержки приёмника: ожидание картинки после LOAD, пауза перед
        #: повтором, часы сторожа подвиса. Умолчание - настоящее время; сухому прогону
        #: сюда дают свои часы, чтобы не выжидать эти минуты (:class:`torrcast.ports.clock.Clock`).
        self.clock: Clock = clock if clock is not None else SystemClock()
        self._cast: Any = None
        self._url = ""
        self._title = ""
        self._peak = 0.0
        self._stall_at = -1.0
        self._stall_since = 0.0
        self._stall_hits = 0
        self._reloads = 0
        self._started = False
        #: С какой секунды фильма грузили показ: повтор LOAD должен попадать туда же.
        self._at = 0.0
        #: Сессия приложения приёмника, которую подняли мы (см. :meth:`_ours`).
        self._session = ""
        #: Позиция с прошлого опроса и незакрытая перемотка (:meth:`_watch_seek`):
        #: откуда прыгнули, куда и с какого монотонного момента ждём картинку.
        self._seen = -1.0
        self._seek_from = 0.0
        self._seek_to = 0.0
        self._seek_since = 0.0
        #: Куда прыгнул наш собственный сторож: его прыжок перемоткой человека не считаем.
        #: Гасится первым же совпадением - на второй прыжок нужен и второй нудж.
        self._nudged_to = -1.0
        #: Сколько нуджей подряд не дали НИ ОДНОГО показанного кадра. Обнуляется только
        #: кадром (``PLAYING``), а не уехавшим указателем: у ушедшего приёмника указатель
        #: как раз послушно едет за каждым ``seek`` (:meth:`_nudge`).
        self._blind = 0
        #: Сторож сдался: лестница нуджей не показала ни кадра, и показ считается
        #: погасшим - дальше его поднимает воскрешение (:class:`torrcast.cli._Revival`).
        self._gone = False
        #: Последний кадр, который зритель ВИДЕЛ перед тем, как сторож начал прыгать;
        #: ``-1`` - никуда не прыгали. Ставится первым прыжком лестницы, а называется
        #: зрителю тогда, когда картинка вернулась и пропуск известен числом
        #: (:meth:`position`). Мерить в момент прыжка нечего: сколько плёнки уйдёт мимо,
        #: решает не прицел, а то место, на котором приёмник в итоге оживёт.
        self._skip_from = -1.0
        #: Последняя подробная причина отказа из сырого ответа приёмника. pychromecast
        #: это поле не переносит в :class:`MediaStatus`, поэтому снимаем его до разбора
        #: ответа (:meth:`_catch_media_error`). ``None`` - за этот LOAD кода не называли:
        #: каждый новый LOAD начинает с чистого (:meth:`_load`), чтобы причина не
        #: переезжала с одной загрузки на следующую.
        self._error_code: int | None = None
        #: Где кончается сегмент, накрывающий эту секунду фильма
        #: (:meth:`torrcast.stream.Grid.after`); ``None`` - сетки не назвали.
        #:
        #: 🔴 Без неё и прыжок сторожа, и подъём после отказа отмеряются абсолютной
        #: секундой, а сегменты разной длины - и оба приземляются в тот же кусок, на
        #: котором показ споткнулся. Ставит её показ (:func:`torrcast.cli._play`): сетку
        #: знает он.
        self.next_cut: Callable[[float], float] | None = None
        #: Сколько раз показ уже умирал на каждом куске; ключ - конец куска, секунды
        #: фильма. Ведётся здесь, а не у показа, потому что спрашивают о нём обе ветки
        #: подъёма - и повтор LOAD (:meth:`_reload`), и воскрешение (:meth:`replay`).
        self._deaths: dict[float, int] = {}
