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
from typing import Final

from torrcast.adapters.browser.clear_web_box import clear_web_box
from torrcast.adapters.browser.clear_web_position import clear_web_position
from torrcast.adapters.browser.read_web_position import read_web_position
from torrcast.adapters.browser.write_web_box import write_web_box
from torrcast.adapters.system_clock import CLOCK
from torrcast.domain.position import Position
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.segment_container import MPEGTS, SegmentContainer
from torrcast.ports.clock import Clock

#: Пока вкладка не прислала ни одной позиции сеанса - показ ждёт первого кадра, тем же
#: словом, каким телевизор отвечает на LOAD до готовности (:data:`torrcast.domain.
#: position.Position.state` пуст до :data:`torrcast.usecases.revive_playback._screen`).
_WAITING = "BUFFERING"
#: Молчание вкладки дольше :attr:`BrowserReceiver.lost_after` и меньше
#: :attr:`BrowserReceiver.gone_after` - самой непроверенной позиции для сравнения нет,
#: есть только её отсутствие.
_LOST = "lost"

# Сроки молчания - про саму вкладку, а не про упаковку: поток ей режется тем же профилем,
# что и телевизору (:func:`torrcast.usecases.worker._cmd_worker`), а своего профиля у неё нет.
#
# Обе границы молчания - слово карточки (ТЗ §7.4: 15 с - «lost», не поднимаем сами;
# 60 с - штатное закрытие тем же путём, каким закрывают потерянный телевизор), а не
# числа, подобранные наблюдением за настоящим декодером: у браузера нет своего
# физического предела терпения, который стоило бы открывать замером. Прогнано живьём
# (``scripts/staleprobe.py``) ровно на то, что код держит эти же секунды, а не другие:
# сеанс встаёт «lost» на 15.0 с молчания и переходит в ``playing=False`` на 60.0 с -
# без единого «почти».
# снято: staleprobe · не при чём · TC-1108
LOST_AFTER: Final = 15.0  # снято: staleprobe · не при чём · TC-1108
GONE_AFTER: Final = 60.0  # снято: staleprobe · не при чём · TC-1108
# Молчание вкладки ловится числом выше, а закрытая вкладка говорит об этом сама
# (``pagehide``/уход с ``/play``, ``player.js``): смысла ждать все 60 с молчания у
# неё нет. 5 с покрывает саму перезагрузку страницы с запасом - живой замер headless
# Chromium на CT502 (``scripts/leftprobe.py``, три перезагрузки ``/play`` подряд): от
# ``pagehide`` до первого свежего доклада ПОСЛЕ ``F5`` неизменно 2.05 с - это цикл
# доклада позиции (``POSITION_MS`` в ``player.js``, 2 с), а не сеть: страница успевает
# переприцепиться к тому же ключу ящика задолго до первого доклада. Переключение
# вкладки слова не шлёт вовсе - для него порог ни при чём. 5 с даёт этому замеру
# больше чем двукратный запас, не подгоняясь под него впритык.
# снято: leftprobe · не при чём · TC-1124
LEFT_AFTER: Final = 5.0  # снято: leftprobe · не при чём · TC-1124


@dataclass(slots=True)
class BrowserReceiver:
    """Приёмник, у которого нет сокета - только два файла и ключ, отличающий сеансы.

    ``out`` - каталог сегментов ЭТОГО показа
    (:func:`torrcast.usecases.playback.hls_root.hls_root`), тот же самый, куда
    :mod:`torrcast.adapters.stream_pack` пишет ``init.mp4`` и ``v*.m4s``: вкладка и
    сегменты, и задание, и позицию берёт по одному и тому же адресу.
    """

    out: Path
    clock: Clock = CLOCK
    #: Сколько секунд вкладка вправе молчать позицией, прежде чем показ пометит её
    #: непроверенной (``state="lost"``) и продолжит ждать - без права поднимать сам:
    #: приёмник без вкладки поднимать нечем (:class:`torrcast.usecases.choice._ctl._Revivable`
    #: у него не реализован намеренно). ``0.0`` - смертью вкладки не мерить.
    lost_after: float = LOST_AFTER
    #: Сколько секунд вкладка вправе молчать позицией, прежде чем сеанс закроют штатным
    #: :func:`torrcast.usecases.playback._show_end._close_show` - тем же путём, каким
    #: кончается потерянный телевизор. ``0.0`` - смертью вкладки не мерить.
    gone_after: float = GONE_AFTER
    #: Столько секунд ждём ПОСЛЕ явного слова страницы «я ухожу» (``phase="left"``,
    #: :mod:`web.position`), прежде чем поверить ему и закрыть сеанс тем же путём, что и
    #: :attr:`gone_after`. Слово это - не молчание, а сигнал ухода со страницы
    #: (закрытие вкладки, переход на другой сайт, уход с ``/play`` внутри приложения), и
    #: ждать его молчанием ``gone_after`` целиком незачем (TC-1124). Перезагрузка и
    #: переключение вкладки под этот срок не подгоняются: обновление переоткрывает ту же
    #: сессию свежим отчётом раньше, чем срок выйдет, а переключение вкладки слова вовсе
    #: не шлёт. ``0.0`` - таким словом не мерить.
    left_after: float = LEFT_AFTER
    #: Профиль приёмника, которым упакован показ, и контейнер его кусков (ставит
    #: :mod:`torrcast.usecases.playback._tract`, как и приёмнику ТВ): оба уходят в ящик, и
    #: «На ТВ» зовёт ТВ с ними, а не с осторожными умолчаниями (:mod:`web.to_tv`).
    profile: Profile = CAUTIOUS
    segment_container: SegmentContainer = MPEGTS
    _key: str = field(default="", init=False)
    _held: float = field(default=0.0, init=False)
    _dur: float = field(default=0.0, init=False)
    _left_pos: float = field(default=-1.0, init=False)

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        """Положить в ящик новое задание со свежим ключом сеанса.

        Свежий ключ - не украшение: старая вкладка, ещё не заметившая новый показ,
        обязана получить 409 на следующей же позиции
        (:mod:`web.position`), а не продолжить писать место чужого сеанса.
        """
        self._key = uuid.uuid4().hex
        self._held, self._dur = at, 0.0
        self._left_pos = -1.0
        clear_web_position(self.out)
        write_web_box(
            self.out,
            url=url,
            title=title,
            at=at,
            key=self._key,
            profile=self.profile.key,
            container=self.segment_container,
        )

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
            return Position(0.0, self._dur, True, _WAITING, known=False)
        pos, dur = float(record.get("pos", 0.0)), float(record.get("dur", 0.0))
        phase = str(record.get("phase", ""))
        self._dur = dur
        since = self.clock.wall() - float(record.get("wall", 0.0))
        if phase == "left":
            # Страница сама сказала «ухожу» (закрытие вкладки, уход с ``/play``,
            # ``player.js``) - ждать молчания незачем, но и верить слову раньше срока
            # нельзя: обновление страницы (``F5``) шлёт то же слово и тут же переприцепляется
            # свежим отчётом (:attr:`left_after`), а от настоящего ухода
            # новый отчёт не приходит никогда.
            # Последний отчёт может быть ровно словом «ухожу»: позиция идёт раз в 2 с,
            # и человек успевает увидеть кадр и уйти между двумя обычными отчётами. Не
            # видеть движение, которое страница положила в ``left``, значило назвать
            # увиденный показ несостоявшимся. Отдаём сначала место, с которого вошли в
            # уход, а следующим опросом само новое: так общий свидетель первого кадра
            # (`_first_frame`) видит именно сдвиг, а не одно недоказуемое слово PLAYING.
            moved = pos > self._held
            if moved and self._left_pos != pos:
                before, self._held, self._left_pos = self._held, pos, pos
                return Position(before, dur, True, "PLAYING")
            if 0.0 < pos < self._held:  # перемотка назад перед самым уходом - место там
                self._held = pos
            if self.left_after > 0.0 and since >= self.left_after:
                return Position(self._held, dur, False, _LOST, stale=True)
            return Position(
                self._held, dur, True, "PLAYING" if moved or self._left_pos == pos else _WAITING
            )
        if pos > 0.0:
            self._held = pos
        if self.gone_after > 0.0 and since >= self.gone_after:
            return Position(self._held, dur, False, _LOST, stale=True)
        if self.lost_after > 0.0 and since >= self.lost_after:
            return Position(self._held, dur, True, _LOST, stale=True)
        if phase == "paused":
            return Position(pos, dur, False, "PAUSED")
        if phase == "ended":
            return Position(pos, dur, False, "IDLE")
        if phase == "buffering":
            return Position(pos, dur, True, "BUFFERING")
        return Position(pos, dur, True, "PLAYING")
