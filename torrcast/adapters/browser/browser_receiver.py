"""Приёмник - вкладка браузера: тот же :class:`torrcast.ports.receiver.Receiver`, что и у ТВ.

Разговор с вкладкой идёт не сокетом, а двумя файлами рядом с сегментами показа
(:mod:`torrcast.adapters.browser.write_web_box`,
:mod:`torrcast.adapters.browser.write_web_position`): задание кладёт этот класс, а место
в нём читает JavaScript страницы через мост
(:mod:`web.box`, :mod:`web.position`). Строку, ушедшую с секцией показа в
:func:`torrcast.usecases.worker._cmd_worker`, ждёт ровно один читатель - следующая
вкладка отличена не адресом, а КЛЮЧОМ сеанса.

🔴 Второй писатель :class:`torrcast.domain.watch_state.WatchState` тут не заведён и не
должен быть: закладку двигает тот же код, что и для приставки, - через
:meth:`position`, а не напрямую из страницы (ТЗ §7.2). Вкладку саму поднять нечем: этот
класс сознательно не реализует :class:`torrcast.usecases.choice._ctl._Revivable`
(нет ``replay()``) - без неё же не поднимешь.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from torrcast.adapters.browser.clear_web_box import clear_web_box
from torrcast.adapters.browser.clear_web_position import clear_web_position
from torrcast.adapters.browser.read_web_position import read_web_position
from torrcast.adapters.browser.write_web_box import write_web_box
from torrcast.adapters.system_clock import CLOCK
from torrcast.domain.position import Position
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.ports.clock import Clock

#: Пока вкладка не прислала ни одной позиции сеанса - показ ждёт первого кадра, тем же
#: словом, каким телевизор отвечает на LOAD до готовности (:data:`torrcast.domain.
#: position.Position.state` пуст до :data:`torrcast.usecases.revive_playback._screen`).
_WAITING = "BUFFERING"
#: Молчание вкладки дольше :attr:`torrcast.domain.receiver_profile.ReceiverProfile.lost_after`
#: и меньше :attr:`~torrcast.domain.receiver_profile.ReceiverProfile.gone_after` - самой
#: непроверенной позиции для сравнения нет, есть только её отсутствие.
_LOST = "lost"


@dataclass(slots=True)
class BrowserReceiver:
    """Приёмник, у которого нет сокета - только два файла и ключ, отличающий сеансы.

    ``out`` - каталог сегментов ЭТОГО показа
    (:func:`torrcast.usecases.playback.hls_root.hls_root`), тот же самый, куда
    :mod:`torrcast.adapters.stream_pack` пишет ``init.mp4`` и ``v*.m4s``: вкладка и
    сегменты, и задание, и позицию берёт по одному и тому же адресу.
    """

    out: Path
    profile: Profile = CAUTIOUS
    clock: Clock = CLOCK
    _key: str = field(default="", init=False)
    _held: float = field(default=0.0, init=False)
    _dur: float = field(default=0.0, init=False)

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        """Положить в ящик новое задание со свежим ключом сеанса.

        Свежий ключ - не украшение: старая вкладка, ещё не заметившая новый показ,
        обязана получить 409 на следующей же позиции
        (:mod:`web.position`), а не продолжить писать место чужого сеанса.
        """
        self._key = uuid.uuid4().hex
        self._held, self._dur = at, 0.0
        clear_web_position(self.out)
        write_web_box(self.out, url=url, title=title, at=at, key=self._key)

    def stop(self, quit_app: bool = False) -> None:
        """Снять задание и позицию: вкладке больше нечего играть и некому отвечать.

        ``quit_app`` тут не разбирают: у вкладки нет отдельного приложения, которое
        стоило бы держать открытым на стыке серий, - следующая же :meth:`play` кладёт
        новое задание, и вкладка перечитывает ящик сама.
        """
        del quit_app
        clear_web_box(self.out)
        clear_web_position(self.out)
        self._key = ""

    def position(self, front: float = 0.0) -> Position:
        """Место показа: своё слово, слово вкладки или заключение о её молчании.

        ``front`` не спрашивается: у вкладки нет своего сторожа подвиса на стороне
        показа - её кормит ``hls.js`` тем же манифестом ``#EXT-X-ENDLIST``, что и любого
        зрителя (:mod:`torrcast.usecases.playback.hls_root`), и нагонять его нечем.
        """
        del front
        record = read_web_position(self.out)
        if record is None or record.get("key") != self._key:
            return Position(self._held, self._dur, True, _WAITING)
        pos, dur = float(record.get("pos", 0.0)), float(record.get("dur", 0.0))
        phase = str(record.get("phase", ""))
        self._dur = dur
        if pos > 0.0:
            self._held = pos
        since = self.clock.wall() - float(record.get("wall", 0.0))
        if self.profile.gone_after > 0.0 and since >= self.profile.gone_after:
            return Position(self._held, dur, False, _LOST, stale=True)
        if self.profile.lost_after > 0.0 and since >= self.profile.lost_after:
            return Position(self._held, dur, True, _LOST, stale=True)
        if phase == "paused":
            return Position(pos, dur, False, "PAUSED")
        if phase == "ended":
            return Position(pos, dur, False, "IDLE")
        if phase == "buffering":
            return Position(pos, dur, True, "BUFFERING")
        return Position(pos, dur, True, "PLAYING")
