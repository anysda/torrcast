"""Сухой приёмник: headless-клиент HLS, на котором едет автономная приёмка."""

from __future__ import annotations

import subprocess
import threading
from typing import Any, Final

from torrcast.adapters.chromecast.mock.hls_decoder import HlsDecoder
from torrcast.adapters.chromecast.mock.hls_fetch import HlsFetch
from torrcast.adapters.chromecast.mock.mock_replay import _replay_paused, mock_replay
from torrcast.adapters.chromecast.mock.mock_settings import _Settings
from torrcast.adapters.chromecast.mock.screen_watch import ScreenWatch
from torrcast.adapters.chromecast.mock.segment_audit import SegmentAudit
from torrcast.adapters.system_clock import SystemClock
from torrcast.domain.not_raised import NOT_RAISED
from torrcast.domain.patience import Patience
from torrcast.domain.position import Position
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.reception_report import ReceptionReport
from torrcast.ports.clock import Clock

#: Часы боевого пути: объект без состояния, заводить свои незачем.
_CLOCK: Final[Clock] = SystemClock()


class MockReceiver(_Settings):
    """Приёмник без телевизора: тянет HLS ровно как ТВ и декодирует ffmpeg'ом.

    Приёмка ТРАНСПОРТА и ДЕКОДА проходит на нём целиком: манифест и сегменты забираются
    тем же транспортом, что у ТВ, с проверкой CORS и непрерывности нумерации
    (:class:`SegmentAudit`), картинку считает настоящий ffmpeg (:class:`HlsDecoder`), а
    терпение к пропавшей картинке моделируется нарочно (:class:`ScreenWatch`) - без него
    целый класс аварий, «источник моргнул под показом», на сухом прогоне не проверялся бы
    вовсе.

    🔴 Чего он не моделирует - **темп**: фильм проигрывается за секунды стенных часов, а
    не в реальном времени. Поэтому зелёный сухой прогон приёмкой прогрева фильма на диск
    не является: сколько прогрев успевает за минуту показа, видно только на живом ТВ.

    Повадки приёмника тут не прибиты константами: терпение, перезаборы куска и обида на
    404 приходят из профиля (:mod:`torrcast.domain.profile`), а константы класса остаются
    умолчанием осторожного профиля.
    """

    def __init__(
        self,
        ca: str = "",
        patience: float = 0.0,
        profile: Profile = CAUTIOUS,
        clock: Clock = _CLOCK,
        spawn: Any = subprocess.Popen,
        thread: Any = threading.Thread,
    ) -> None:
        self.ca = ca
        #: Чей приёмник изображаем: у профиля своё терпение, свои перезаборы и своя обида
        #: на 404. Умолчание осторожное - тот аппарат, на котором всё замерено.
        self.profile = profile
        self.patience = patience or profile.patience
        #: Чем меряется терпение. Умолчание - настоящее время; сухому прогону сюда дают
        #: свои часы, чтобы не выжидать секунды и не зависеть от загрузки машины.
        self.clock = clock
        self.thread = thread
        self.report = ReceptionReport()
        self.fetch = HlsFetch(ca, clock, profile.sulk)
        self.decoder = HlsDecoder(self.report, ca, spawn, thread)
        self.audit = SegmentAudit(self.report, self.fetch)
        self.screen = ScreenWatch(
            self.decoder,
            self.report,
            profile,
            Patience(self.patience, profile.segment_retries),
            clock,
            lambda pos: self._open(self._url, pos),
        )
        #: Чем и подо что грузили: повтор LOAD уходит туда же, куда и первый.
        self._url = ""
        #: Почему последний подъём не дал картинки; пусто - подъёма не было либо он удался.
        #: Слова тут живые («нельзя», «упал», «не взял»): замер подъёмов читают по ленте, а
        #: не по тракту, который её вёл (:meth:`refusal`).
        self._refused = ""

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        del title  # названия сухому приёмнику показывать негде
        self._url = url
        self.screen.reset()
        self._open(url, at)

    def seek(self, pos: float) -> None:
        """Перемотка с диагностического пульта.

        ⚠️ Чем это отличается от живого приёмника, и отличие не убирается: ТВ мотает
        внутри той же медиасессии, а тут декодер приходится открывать заново. Снаружи
        разница видна: после перемотки приёмник ненадолго уходит в ``BUFFERING``, как
        после LOAD. Что накоплено до первого кадра, заново не разыгрывается: копит
        приёмник один раз, на заходе.
        """
        self.screen.paused = False
        self._open(self._url, pos)
        self.screen.jumped(pos)

    def pause(self) -> None:
        """Пауза с пульта: декодер умолкает, а сессия и место на экране остаются.

        Приёмник на паузе перестаёт брать сегменты - и тут перестаёт, поэтому упаковка
        гаснет по той же причине и на той же секунде, а показ считается живым.

        ⚠️ Отличие от ТВ, которое не убрать: там пауза не трогает медиасессию, а тут
        декодер приходится остановить и на :meth:`resume` открыть заново. Держать его
        замороженным сигналом нельзя: ``SIGSTOP`` в коде показа запрещён - под ним
        приёмник намертво вис в ``BUFFERING`` при живых сегментах на диске.
        """
        self.screen.paused = True
        self.decoder.stop()

    def resume(self) -> None:
        """Снять паузу: показ продолжается ровно с того места, где стоял."""
        if not self.screen.paused:
            return
        self.screen.paused = False
        pos = self.decoder.pos.pos
        self.screen.jumped(pos)
        self._open(self._url, pos)

    def volume(self, step: float) -> None:
        """Сухому экрану громкость негде воспроизводить."""
        del step

    def stop(self, quit_app: bool = False) -> None:
        """Снять каст. Приложения тут нет, поэтому ``quit_app`` нечего закрывать -
        аргумент есть затем, чтобы сухой приёмник оставался приёмником
        (:class:`torrcast.ports.receiver.Receiver`).
        """
        del quit_app
        self.decoder.stop()

    def position(self, front: float = 0.0) -> Position:
        """Что приёмник видит на экране; ``front`` - докуда упаковано."""
        return self.screen.read(front)

    def replay(self, at: float, paused: bool = False) -> float:
        """Поднять СВОЙ погасший показ с секунды ``at`` (:func:`mock_replay`).

        ⚠️ Чужой показ он не видит и видеть не может: что приёмник занят чужим, проверяется
        только на живом ТВ.

        ``paused=True`` - вернуть сессию на закладку, НЕ начиная показ: паузу ставил
        зритель, и снимает её тоже он, с пульта.
        """
        if not self._url:
            self._refused = "нельзя: показ сюда не заводили"
            return NOT_RAISED
        if self.clock.monotonic() < self.fetch.sulk_until:
            self._refused = "нельзя: приёмник помнит 404 и LOAD не берёт"
            return NOT_RAISED
        if paused:
            at, self._refused = _replay_paused(
                lambda pos: self._open(self._url, pos), self.screen, self.pause, at
            )
            return at
        at, self._refused = mock_replay(
            lambda pos: self._open(self._url, pos),
            self.screen,
            self.decoder,
            self.clock,
            at,
            self.WAKE_TIMEOUT,
        )
        return at

    def refusal(self) -> str:
        """Почему последний :meth:`replay` не дал картинки; пусто - он удался.

        Тот же ответ и теми же словами, что у живого приёмника
        (:meth:`torrcast.adapters.chromecast.cast.chromecast_receiver.ChromecastReceiver.refusal`):
        сухой прогон затем и нужен, чтобы по нему судить о живом, а лента, у которой поля
        не те же, судить не даёт.
        """
        return self._refused

    def _open(self, url: str, at: float = 0.0) -> None:
        """Спросить источник, завести декодер и пустить за ним сверку сегментов.

        Порядок обязателен: сперва спрашиваем источник и только потом рушим прошлый
        декодер, иначе неудачный повтор гасил бы ещё живую картинку.
        """
        body = self.fetch.manifest(url)  # первый ответ проверяем сами: TLS, доступность, CORS
        self.decoder.open(url, body, at)
        watcher = self.thread(
            target=self.audit.run,
            args=(url, at, lambda: self.decoder.pos.pos, self.decoder.done),
            daemon=True,
        )
        watcher.start()
