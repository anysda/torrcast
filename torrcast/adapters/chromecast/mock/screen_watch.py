"""Учёт экрана: идёт ли картинка, ждём ли её и жива ли ещё медиасессия."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.adapters.chromecast.mock.hls_decoder import HlsDecoder
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.ending_reached import ending_reached
from torrcast.domain.first_frame_ready import first_frame_ready
from torrcast.domain.infra_error import InfraError
from torrcast.domain.patience import Patience
from torrcast.domain.position import Position
from torrcast.domain.profile import Profile
from torrcast.domain.reception_report import ReceptionReport
from torrcast.domain.why import why
from torrcast.ports.clock import Clock
from torrcast.ports.journal.slot import journal


class ScreenWatch:
    """Что приёмник видит на экране - и сколько он готов это терпеть.

    Ожидание тут не бутафория: у живого приёмника терпение своё и кончается молча,
    поэтому и сухой сперва терпит стоящую картинку, а потом бросает показ насовсем.
    Внутри терпения он пробует поднять себя сам - те самые перезаборы куска, разнесённые
    по терпению поровну (``reopen``). Разницу видно снаружи ровно так же, как на ТВ: пока
    терпит - ``BUFFERING`` и показ считается живым, бросил - ``IDLE``.
    """

    def __init__(
        self,
        decoder: HlsDecoder,
        report: ReceptionReport,
        profile: Profile,
        patience: Patience,
        clock: Clock,
        reopen: Callable[[float], None],
    ) -> None:
        self.decoder, self.report = decoder, report
        self.profile, self.patience, self.clock = profile, patience, clock
        self.reopen = reopen
        #: Приёмник бросил показ: сессии больше нет, позиции в ней тоже.
        self.dead = False
        #: Показ стоит на паузе с пульта: декодер снят, сессия жива.
        self.paused = False
        #: Первый кадр этого показа уже был на экране. До него приёмник копит фильм.
        self.shown = False
        #: Позиция с прошлого опроса: стоящая картинка видна только по ней.
        self.seen = -1.0
        #: С какого монотонного момента картинка стоит; ``0.0`` - она идёт.
        self.still = 0.0
        #: Сколько перезаборов куска потрачено на текущую остановку картинки.
        self.loads = 0

    def reset(self) -> None:
        """Новый показ: экран чист, терпение целое, кадра ещё не было."""
        self.seen, self.still, self.loads = -1.0, 0.0, 0
        self.dead, self.shown, self.paused = False, False, False

    def jumped(self, pos: float) -> None:
        """Показ перенесён на ``pos`` своей волей - перемоткой, снятием паузы, подъёмом.

        Счётчики стоящей картинки сбрасываются нарочно: это не пропавший источник, и
        зачесть такой перенос приёмнику в терпение значило бы гасить показ за то, что
        зритель нажал кнопку.
        """
        self.seen, self.still, self.loads = pos, 0.0, 0

    def read(self, front: float = 0.0) -> Position:
        """Что приёмник видит на экране - картинку, ожидание её или мёртвую сессию."""
        # dur - то, что уже упаковано и лежит в манифесте: показ по нему видит, насколько
        # упаковка ушла вперёд от приёмника. Запас тут ни к чему: он не зависает.
        dur = self.report.duration
        if self.dead:
            # 🔴 У мёртвой сессии позиции нет вовсе - там ноль, и это не перемотка в
            # начало. Ровно так отвечает и живой приёмник, бросив показ; на этом нуле
            # сторож обязан держать своё место сам.
            return Position(0.0, dur, False, "IDLE")
        if self.paused:
            # Пауза с пульта: картинка стоит нарочно, и стоящей её считать нельзя -
            # терпение приёмника тут не тратится, показ жив, место прежнее.
            return Position(self.decoder.pos.pos, dur, True, "PAUSED")
        seen = self.decoder.pos
        pos, moving = seen.pos, seen.pos > self.seen
        self.seen = pos
        if seen.playing and moving and self.buffered(pos, front):
            self.shown = True
            self.still, self.loads = 0.0, 0
            return Position(pos, dur, True, "PLAYING")
        if self.over():
            return Position(pos, dur, False, "")  # декодер дошёл до конца входа - это титры
        if self.wait(pos):
            # Приёмник ждёт картинку и показ считает живым - как ТВ в BUFFERING.
            return Position(pos, dur, True, "BUFFERING")
        return Position(0.0, dur, False, "IDLE")

    def buffered(self, pos: float, front: float) -> bool:
        """Набрал ли показ столько фильма, сколько приёмнику нужно до первого кадра."""
        return first_frame_ready(self.shown, pos, front, self.profile.start_buffer)

    def over(self) -> bool:
        """Кончились ли титры: декодер вышел нулём там, где фильму и положено кончиться."""
        return self.decoder.finished and ending_reached(self.decoder.pos.pos, self.report.duration)

    def wait(self, pos: float) -> bool:
        """Терпение к стоящей картинке; ``False`` - оно кончилось, показ брошен."""
        now = self.clock.monotonic()
        self.still = self.still or now
        dark = now - self.still
        if self.patience.gave_up(dark):
            self.dead = True
            self.decoder.stop()
            return False
        if self.patience.retry_due(dark, self.loads):
            self.loads += 1
            self.retry(pos)
        return True

    def retry(self, pos: float) -> None:
        """Перезабрать кусок самому - и сказать в ленту, что перезабор был и чем кончился.

        🔴 Молчать тут нельзя. Перезабор не гасит показ и снаружи ничем себя не выдаёт,
        поэтому лента - единственное место, где он вообще существует: без записи замер,
        считающий по ней, видит один заход там, где их было четыре, а пустота «перезаборов
        не было» неотличима от пустоты «все перезаборы легли».

        Отказ называется теми же словами, что и у подъёма
        (:func:`torrcast.adapters.chromecast.mock.mock_replay.mock_replay`): сухую ленту
        затем и читают, чтобы судить о живой, и разводить в ней словари незачем.

        ⚠️ ``ok`` тут - «перезабор ушёл», а НЕ «картинка вернулась». Вернулась она или нет,
        решает следующий опрос экрана: назвать отправленный запрос картинкой значило бы
        соврать ровно там, где живой тракт врать уже перестал.
        """
        said = ""
        try:
            self.reopen(pos)
        except (InfraError, OSError) as exc:
            # источника всё ещё нет - терпим дальше
            said = phrase("chromecast_talk.refused_crashed", reason=why(exc))
        journal().refetch(pos=pos, tries=self.loads, ok=not said, why=said)
