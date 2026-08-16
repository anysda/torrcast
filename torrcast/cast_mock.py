"""Сухой приёмник: headless-клиент HLS, на котором едет автономная приёмка.

``mock`` не заглушка «для галочки»: он тянет манифест и сегменты тем же транспортом, что
и ТВ, проверяет CORS и непрерывность нумерации, декодирует ffmpeg'ом и отдаёт позицию. На
нём проходит приёмка ТРАНСПОРТА и ДЕКОДА, но не всего показа: mock проигрывает фильм за
секунды стенных часов, а не в реальном темпе, и вторая голова чтения - прогрев фильма на
диск (:mod:`torrcast.warm`) - под ним не появляется вовсе. Значит зелёный сухой прогон
доказывает раздачу и декод, но НЕ прогрев; сам прогрев проверяется отдельно
(tests/test_warm.py, живой ТВ). Подробности - в докстринге :class:`MockReceiver`.

⚠️ Повадки приёмников тут ЕСТЬ - терпение к пустому экрану, число перезаборов куска, -
но ни одно из этих чисел не прибито константой: все они приходят из профиля
(:mod:`torrcast.profile`), а константы класса остаются умолчанием осторожного профиля.
"""

from __future__ import annotations

import contextlib
import math
import os
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from typing import IO, Any

from torrcast import InfraError, why
from torrcast.cast_core import Position
from torrcast.profile import CAUTIOUS, Profile
from torrcast.state import WATCHED_RATIO
from torrcast.stream import parse_manifest
from torrcast.timing import CLOCK, Clock

__all__ = [
    "MockReceiver",
    "Report",
]

#: Номер сегмента в имени ``index<N>.ts`` - по нему ловятся дыры в нумерации.
_NUM_RE = re.compile(r"(\d+)\.ts$")
#: Строки ffmpeg, означающие, что кусок не доехал: для приёмки это разрыв.
_LOST_RE = re.compile(r"Failed to open segment|Error opening|Cannot reload|skipping", re.I)
_CORS_HEADER = "Access-Control-Allow-Origin"
#: На сколько секунд вперёд декодера mock позволяет себе спрашивать сегменты.
_AUDIT_AHEAD = 8.0
#: Допуск, с которым место захода ложится на сетку манифеста (:meth:`MockReceiver._from`).
#: ``EXTINF`` округлён до шести знаков, и сумма таких длительностей не совпадает с границей
#: сетки бит в бит: 10.023222 + 10 + 10 + 10 + 10 даёт 50.02322200000001, и заход ровно на
#: эту границу съезжал бы на кусок НАЗАД - то есть тащил бы за собой упаковку, ради чего
#: голова плейлиста и срезается.
_GRID_SLACK = 0.001
#: Что разрешено декодеру, когда плейлист подан ему файлом (:meth:`MockReceiver._from`):
#: сам файл и сеть, в которой лежат сегменты. Без списка ffmpeg отказывается ходить с
#: диска наружу («Protocol 'http' not on whitelist») и не открывает вход вовсе.
_PROTOCOLS = "file,http,https,tcp,tls,crypto,data"


@dataclass(slots=True)
class Report:
    """Что mock увидел как приёмник — цифры приёмки."""

    segments: int = 0
    duration: float = 0.0
    decoded: float = 0.0
    gaps: int = 0
    peak_mbit: float = 0.0
    #: Ответы без ``Access-Control-Allow-Origin``: Chromecast на таких молча молчит.
    no_cors: int = 0

    @property
    def ok(self) -> bool:
        """Приёмка: дыр нет, CORS везде, декодировано до конца (хвост в один сегмент)."""
        return (
            self.segments > 0
            and self.gaps == 0
            and self.no_cors == 0
            and self.decoded >= self.duration - 8.0
        )

    def line(self) -> str:
        return (
            f"сегментов {self.segments} · манифест {self.duration:.0f} с · "
            f"декодировано {self.decoded:.0f} с · разрывов {self.gaps} · "
            f"без CORS {self.no_cors} · пик {self.peak_mbit:.1f} Мбит/с"
        )


class MockReceiver:
    """Headless-приёмник: тянет HLS ровно как ТВ и декодирует ffmpeg'ом в ``/dev/null``.

    Адрес приходит готовым, и по нему же выбирается строгость: на https TLS проверяется
    по-настоящему, а не ``verify=False`` — чему доверять, решает :func:`trust_anchor`
    (системное хранилище для настоящего LE-серта, ровно как у ТВ, или сам файл для
    self-signed; пустой ``ca`` = хранилище). На http проверять нечего.

    Терпение к пропавшей картинке mock моделирует нарочно (:attr:`PATIENCE`,
    :meth:`replay`): без него целый класс аварий - «источник моргнул под показом» - на
    сухом прогоне не проверялся вовсе, потому что заглушка показ не бросала никогда и
    воскрешать в ней было нечего. Модель держится на замерах живого Q70D и ничего сверх
    них не обещает; чего она не умеет - сказано у :attr:`PATIENCE` и :meth:`replay`.
    ⚠️ Прежняя приписка («терпение и повторы LOAD - это поведение самого Default Media
    Receiver, а не трюки вокруг телевизора») опровергнута: на приставке Android TV тот же
    Default Media Receiver ведёт себя иначе - мёртвый URL стоит ей одного запроса и
    ``IDLE/ERROR`` на 4-й секунде, перезаборов куска ноль. Значит это повадки КОНКРЕТНОГО
    приёмника, и берутся они из его профиля (:mod:`torrcast.profile`), а не из класса.

    🔴 Чего mock НЕ моделирует: **темп** второй головы чтения - прогрева фильма на диск
    (:mod:`torrcast.warm`). Прогрев работает впрок в фоне на протяжении ВСЕГО показа и
    трогается с места при играющей картинке, на остатке процессора, а mock проигрывает
    фильм за секунды стенных часов, а не в реальном темпе: соотношение «сколько прогрев
    успел за минуту показа» под заглушкой не значит ничего.

    ⚠️ Прежняя приписка («вторая голова под заглушкой не появляется ни разу, а
    :meth:`torrcast.warm.Warmer._run` за сухой прогон не зовётся вовсе») ОПРОВЕРГНУТА
    замером: на заглушке прогрев работает - в прогоне TC-162 он дорос до 0:16:28, живой
    ``nice -19 ffmpeg -readrate 4`` виден среди потомков воркера. Так и устроено: прогрев
    заводится по одному только ``config.warm`` и о приёмнике не спрашивает вовсе
    (:func:`torrcast.playback._warmer`), а ожидание запаса под заглушкой упирается в
    потолок :data:`torrcast.warm.START_GRACE` и кончается само
    (:meth:`torrcast.warm.Warmer._wait_for_picture`). Считать сухие замеры прогрева
    несуществующими нельзя - они есть, просто темп в них не настоящий.

    Поэтому зелёный сухой прогон приёмкой ПРОГРЕВА не является: сам прогрев
    сверяется отдельно, гоняя :class:`torrcast.warm.Warmer` напрямую (tests/test_warm.py),
    и на живом ТВ с выключенным интернетом.

    ⚠️ Сделать заглушку реально-темповой, чтобы прогрев шёл в ней «как на живом», нельзя:
    сухой прогон стал бы длиться как сам фильм и потерял бы детерминизм, ради которого он
    и существует, а прогрев всё равно не успел бы уложить фильм за один прогон показа. Это
    осознанная граница модели, а не недоделка: под заглушкой честно проверяется, что
    прогрев ЗАВОДИТСЯ и не мешает показу, а сколько он успевает - только на живом ТВ.
    """

    #: Сколько приёмник терпит стоящую картинку, прежде чем умрёт медиасессия. Замер
    #: 09-08-2026 на живом Q70D (рапорт приёмника + tcpdump): 23.5 с. Прежние «около
    #: четырёх минут» склеивали этот срок со сроком жизни приложения на экране
    #: (:attr:`torrcast.profile.Profile.app_patience`) и не равны ни одному из них.
    #: Терпение задаётся и в конструкторе: тест не обязан выжидать даже эти секунды.
    PATIENCE = CAUTIOUS.patience
    #: Сколько раз приёмник САМ перезабирает пропавший кусок, прежде чем сдаться.
    #: ⚠️ Не «повторы LOAD»: ``media_session_id`` при этом не меняется, приёмник
    #: переспрашивает тот же кусок по HTTP (:attr:`torrcast.profile.Profile.segment_retries`).
    #: У Q70D их два, у приставки Android TV - ни одного.
    SEGMENT_RETRIES = CAUTIOUS.segment_retries
    #: Сколько приёмник не берёт LOAD вовсе, поймав 404. 🔴 Ноль, и это замер, а не
    #: упрощение: наказание за 404 опровергнуто трижды (:attr:`torrcast.profile.Profile.sulk`).
    #: Заглушка наказывала за 404 две с половиной минуты - и ровно этого на живом ТВ нет.
    SULK = CAUTIOUS.sulk
    #: Сколько ждём картинку, поднимая погасший показ (:meth:`replay`) - как у живого
    #: приёмника: попытка тут не одна, интервалы держит зовущий.
    WAKE_TIMEOUT = 60.0

    def __init__(
        self,
        ca: str = "",
        patience: float = 0.0,
        profile: Profile = CAUTIOUS,
        clock: Clock = CLOCK,
    ) -> None:
        self.ca = ca
        #: Чей приёмник изображаем: у профиля своё терпение, свои повторы и своя обида
        #: на 404. Умолчание осторожное - тот самый Q70D, на котором всё замерено.
        self.profile = profile
        self.patience = patience or profile.patience
        #: Чем меряется терпение (:meth:`_wait`, :meth:`replay`). Умолчание - настоящее
        #: время; сухому прогону сюда дают свои часы, чтобы не выжидать эти секунды и не
        #: зависеть от загрузки машины (:class:`torrcast.timing.Clock`).
        self.clock = clock
        self.report = Report()
        self._proc: subprocess.Popen[str] | None = None
        self._err: IO[bytes] | None = None
        self._pos = Position(0.0, 0.0, False)
        self._done = threading.Event()
        self._start = 0.0
        self._last = -1
        self._follower: threading.Thread | None = None
        #: Чем и подо что грузили: повтор LOAD уходит туда же, куда и первый.
        self._url = ""
        #: Позиция с прошлого опроса: стоящая картинка видна только по ней.
        self._seen = -1.0
        #: С какого монотонного момента картинка стоит; ``0.0`` - она идёт.
        self._still = 0.0
        #: Сколько повторов LOAD потрачено на текущую остановку картинки.
        self._loads = 0
        #: Приёмник бросил показ: сессии больше нет, позиции в ней тоже.
        self._dead = False
        #: Докуда приёмник не берёт LOAD после пойманного 404 (:attr:`SULK`).
        self._sulk = 0.0
        #: Временный плейлист со срезанной головой (:meth:`_from`); пусто - декодер
        #: открывается по адресу раздачи, резать было нечего.
        self._list = ""
        #: Первый кадр этого показа уже был на экране. До него приёмник копит фильм
        #: (:attr:`torrcast.profile.Profile.start_buffer`), после - идёт как шёл.
        self._shown = False
        #: Показ стоит на паузе с пульта (:meth:`pause`): декодер заморожен, сессия жива.
        self._paused = False

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        self._url = url
        self._seen, self._still, self._loads, self._dead = -1.0, 0.0, 0, False
        self._shown, self._paused = False, False
        self._open(url, at)

    def seek(self, pos: float) -> None:
        """Перемотка с диагностического пульта (:data:`torrcast.cli.CTL_ENV`).

        Пульт для того и заведён, что кнопку нажать может только человек, а сухому
        прогону перемотку проверять больше нечем. Без этих трёх методов заглушка не
        проходила :class:`torrcast.cli._Steerable`, и команда пульта молча оставалась
        лежать файлом: «на mock перемотка работает» доказывалось ничем.

        ⚠️ Чем это отличается от живого приёмника, и отличие не убирается: ТВ мотает
        внутри той же медиасессии, а заглушке декодер приходится открывать заново
        (:meth:`_open`) - у неё нет ничего другого. Снаружи разница видна: после
        перемотки заглушка ненадолго уходит в ``BUFFERING``, как после LOAD. Что накоплено
        до первого кадра, заново не разыгрывается: копит приёмник один раз, на заходе
        (:meth:`_buffered`), а перемотка - не заход.
        """
        self._paused = False
        self._open(self._url, pos)
        self._seen, self._still, self._loads = pos, 0.0, 0

    def pause(self) -> None:
        """Пауза с пульта: декодер умолкает, а сессия и место на экране остаются.

        Приёмник на паузе перестаёт брать сегменты - и заглушка перестаёт, поэтому
        упаковка гаснет по той же причине и на той же секунде
        (:data:`torrcast.cli.PAUSE_SECONDS`), а показ считается живым.

        ⚠️ Отличие от ТВ, которое не убрать: там пауза не трогает медиасессию, а тут
        декодер приходится остановить и на :meth:`resume` открыть заново. Держать его
        замороженным сигналом нельзя: ``SIGSTOP`` в коде показа запрещён - под ним
        приёмник намертво вис в ``BUFFERING`` при живых сегментах на диске
        (tests/test_hls.py). Снаружи разница видна одним: снятая пауза стоит заглушке
        того же ожидания картинки, что и LOAD.
        """
        self._paused = True
        self._quiet()

    def resume(self) -> None:
        """Снять паузу: показ продолжается ровно с того места, где стоял.

        Счётчики стоящей картинки сбрасываются нарочно: пауза - не пропавший источник, и
        зачесть её приёмнику в терпение (:meth:`_wait`) значило бы гасить показ за то,
        что зритель нажал кнопку.
        """
        if not self._paused:
            return
        self._paused = False
        self._seen, self._still, self._loads = self._pos.pos, 0.0, 0
        self._open(self._url, self._pos.pos)

    def _open(self, url: str, at: float = 0.0) -> None:
        """Открыть поток с секунды ``at``: проверка ответа, декодер, счётчики приёмки.

        Зовётся и на первый LOAD, и на каждый повтор — свой (:meth:`_wait`) и чужой
        (:meth:`replay`). Порядок обязателен: сперва спрашиваем источник и только потом
        рушим прошлый декодер, иначе неудачный повтор гасил бы ещё живую картинку.
        """
        body = self._probe(url)  # первый ответ проверяем сами: TLS, доступность, CORS
        self._quiet()
        self._done = threading.Event()  # прошлые потоки остановлены, у этого показа свой
        self._last = -1  # нумерация сегментов пойдёт с места подъёма, а не подряд с прошлой
        self._err = tempfile.TemporaryFile()  # noqa: SIM115 - живёт всё воспроизведение
        self._start = at
        source, offset = self._from(url, body, at)
        head: list[str] = []
        if source != url:
            head = ["-protocol_whitelist", _PROTOCOLS]
        elif url.startswith("https://"):
            # ⚠️ Опции TLS ставятся только под https-адрес: на http ffmpeg не «игнорирует
            # лишнее», а падает с «Option tls_verify not found» ещё до открытия входа -
            # то есть на дефолтном транспорте mock не декодировал бы ничего.
            head = ["-tls_verify", "1", *(["-ca_file", self.ca] if self.ca else [])]
        command = [
            "ffmpeg", "-hide_banner", "-nostats", "-loglevel", "warning", *head,
            *(["-ss", f"{offset:.3f}"] if offset > 0 else []),
            "-i", source, "-progress", "pipe:1", "-f", "null", "-",
        ]  # fmt: skip
        try:
            self._proc = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=self._err, text=True
            )
        except FileNotFoundError as exc:
            self._close_log()
            raise InfraError("ffmpeg не установлен") from exc
        # 🔴 Место захода, а не ноль: до первого слова декодера приёмник стоит ТАМ, КУДА
        # его послали, и живой Q70D отвечает ровно так (указатель держится на месте захода,
        # пока приёмник копит фильм). С нулём заглушка на первом же опросе отматывала показ
        # в начало фильма - продолжение с 0:20:00 читалось как 0:00:00, и закладку сухим
        # прогоном проверить было нельзя вовсе.
        self._pos = Position(at, 0.0, True)
        self._follower = None
        for target in (self._follow, self._audit):
            thread = threading.Thread(target=target, args=(url,), daemon=True)
            thread.start()
            if target is self._follow:
                self._follower = thread

    def _from(self, url: str, body: str, at: float) -> tuple[str, float]:
        """Чем кормить декодер, чтобы он начал ровно там, откуда начинает приёмник.

        🔴 ``ffmpeg -ss`` по адресу плейлиста сперва ОТКРЫВАЕТ вход - забирает самый
        первый сегмент, чтобы опознать дорожки, - и только потом перематывается. Раздача
        видит запрос первого куска и уходит паковать с нуля, поэтому в сухом замере
        продолжения с середины всегда виден лишний заход упаковки на слот 0. Живой Q70D
        (три прогона, ноль запросов первого сегмента) головы плейлиста не трогает вовсе:
        LOAD с ``current_time`` спрашивает тот кусок, в который целится, и дальше идёт
        вперёд. Ложный дефект «показ пакует голову плейлиста при старте с середины»
        родился ровно на этом отличии заглушки и стоил живого замера.

        Поэтому декодеру достаётся не адрес плейлиста, а плейлист со срезанной головой:
        те же куски начиная с нужного, адресами на ту же раздачу. Открывается ffmpeg тем
        самым куском, остаток забирает по сети подряд, как ТВ, а ``-ss`` остаётся ровно
        остатком ВНУТРЬ куска - позиция не разъезжается с запрошенной.

        Резать нечего - вход остаётся прежним: заход в первый же кусок и так начинается с
        головы, а манифест без ``ENDLIST`` (растущий) обрезать нельзя - там ещё не
        известно, что будет дальше. Показ раздаёт манифест VOD на весь фильм
        (:meth:`torrcast.stream.Grid.manifest`), так что срезать есть что всегда.

        ⚠️ Опции TLS с таким входом ffmpeg не принимает вовсе («Option tls_verify not
        found»), и потерять с ними нечего: замерено, что в запросы сегментов ffmpeg их не
        передаёт ни на каком входе - плейлист с сертом одного CA и сегменты с сертом
        другого декодируются молча. Единственную настоящую проверку серта раздачи делает
        не декодер, а :meth:`_probe` (и :meth:`_audit`) через ``requests``, и она остаётся
        на месте при любом заходе.

        ⚠️ Что от живого приёмника всё же отличается, и это НЕ дефект показа: заход в
        середину куска стоит заглушке ДВУХ запросов одного и того же куска - ffmpeg
        открывает им вход и, домотав внутрь, забирает его снова. Ложного захода упаковки
        из этого не выходит: оба запроса приходятся на кусок, который показ уже пакует, и
        никуда её не двигают. Заход ровно на границу куска обходится одним запросом.
        """
        if at <= 0:
            return url, at
        segments, ended = parse_manifest(body)
        if not ended or not segments:
            return url, at
        starts: list[float] = []
        clock = 0.0
        for _, seconds in segments:
            starts.append(clock)
            clock += seconds
        first = max((s for s, start in enumerate(starts) if start <= at + _GRID_SLACK), default=0)
        if first == 0:
            return url, at
        base = url.rsplit("/", 1)[0]
        lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            f"#EXT-X-TARGETDURATION:{max(1, math.ceil(max(s for _, s in segments)))}",
            f"#EXT-X-MEDIA-SEQUENCE:{first}",
            "#EXT-X-PLAYLIST-TYPE:VOD",
        ]
        for name, seconds in segments[first:]:
            lines += [f"#EXTINF:{seconds:.6f},", f"{base}/{name}"]
        lines.append("#EXT-X-ENDLIST")
        self._drop_list()  # плейлист живёт один заход, и прошлый уходит вместе с ним
        handle, self._list = tempfile.mkstemp(suffix=".m3u8")
        with os.fdopen(handle, "w", encoding="utf-8") as playlist:
            playlist.write("\n".join(lines) + "\n")
        return self._list, max(0.0, at - starts[first])

    def _close_log(self) -> None:
        """Закрыть журнал ffmpeg и убрать срезанный плейлист (:meth:`_from`) - оба живут
        ровно один заход декодера. Зовётся с двух сторон, поэтому забирает файлы себе.
        """
        err, self._err = self._err, None
        if err is not None:
            err.close()
        self._drop_list()

    def _drop_list(self) -> None:
        """Убрать срезанный плейлист прошлого захода; забирает путь себе, зовут с двух сторон."""
        cut, self._list = self._list, ""
        if cut:
            with contextlib.suppress(OSError):
                os.unlink(cut)

    def stop(self, quit_app: bool = False) -> None:
        """Снять каст. Приложения у mock нет, поэтому ``quit_app`` ему нечего закрывать —
        аргумент есть только затем, чтобы mock оставался приёмником (:class:`Receiver`).
        """
        self._quiet()

    def _quiet(self) -> None:
        """Остановить декодер и его потоки: показ снимают либо грузят заново."""
        self._done.set()
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._proc.wait(timeout=5)
        # Журнал ffmpeg дочитывает :meth:`_follow` - он же его и закроет; ждём его, чтобы
        # не отнять счёт разрывов, и закрываем сами, если он не дошёл или не заводился.
        if self._follower is not None:
            self._follower.join(timeout=5)
        self._follower = None
        self._close_log()
        self._pos = Position(self._pos.pos, self._pos.dur, False)

    def position(self, front: float = 0.0) -> Position:
        """Что приёмник видит на экране — картинку, ожидание её или мёртвую сессию.

        Ожидание тут не бутафория: у живого приёмника терпение своё и кончается молча,
        поэтому и заглушка стоящую картинку сперва терпит (:meth:`_wait`), а потом бросает
        показ насовсем. Разницу видно снаружи ровно так же, как на ТВ: пока терпит -
        ``BUFFERING`` и показ считается живым, бросил - ``IDLE``, и поднимать его теперь
        некому, кроме :meth:`replay`.
        """
        # dur - то, что уже упаковано и лежит в манифесте: показ по нему видит, насколько
        # упаковка ушла вперёд от приёмника. Запас mock'у ни к чему: он не зависает.
        dur = self.report.duration
        if self._dead:
            # 🔴 У мёртвой сессии позиции нет вовсе - там ноль, и это не перемотка в начало.
            # Ровно так отвечает и живой Q70D, бросив показ; на этом нуле сторож обязан
            # держать своё место сам (:class:`torrcast.cli._Revival`).
            return Position(0.0, dur, False, "IDLE")
        if self._paused:
            # Пауза с пульта: картинка стоит нарочно, и стоящей её считать нельзя -
            # терпение приёмника тут не тратится, показ жив, место прежнее.
            return Position(self._pos.pos, dur, True, "PAUSED")
        pos, moving = self._pos.pos, self._pos.pos > self._seen
        self._seen = pos
        if self._pos.playing and moving and self._buffered(pos, front):
            self._shown = True
            self._still, self._loads = 0.0, 0
            return Position(pos, dur, True, "PLAYING")
        if self._over():
            return Position(pos, dur, False, "")  # декодер дошёл до конца входа - это титры
        if self._wait(pos):
            # Приёмник ждёт картинку и показ считает живым - как ТВ в BUFFERING.
            return Position(pos, dur, True, "BUFFERING")
        return Position(0.0, dur, False, "IDLE")

    def _buffered(self, pos: float, front: float) -> bool:
        """Набрал ли показ столько фильма, сколько приёмнику нужно до ПЕРВОГО кадра.

        🔴 Замер на живом Q70D (:attr:`torrcast.profile.Profile.start_buffer`): приёмник
        отвечает ``PLAYING``, ещё не показав ни кадра, и держит указатель на месте захода,
        пока не накопит около десяти секунд фильма. Заглушка этого не знала и объявляла
        картинку по первому же сдвигу своего декодера - то есть сухой прогон показывал
        старт на 5-6 с бодрее живого ТВ, и ровно на эти секунды врали все замеры старта.

        Запас показу известен не всегда: ``front <= pos`` значит «впереди не названо
        ничего», и судить тут не о чем - работает прежнее правило. Кадр уже был на
        экране - правило тоже не работает: копит приёмник один раз, на заходе.
        """
        return self._shown or front <= pos or front - pos >= self.profile.start_buffer

    def _over(self) -> bool:
        """Кончились ли титры: декодер вышел нулём ТАМ, где фильму и положено кончиться.

        🔴 Нулевой выход сам по себе титрами не является. Замер TC-314: источник пропал
        под показом, ffmpeg честно закрыл вход нулём на 0:04:42 из 2:46:55 - и сухой
        прогон записал это как «фильм доигран» (в журнале ``экран: 0:04:42`` с пустым
        состоянием). Так любая смерть источника на пятой минуте читалась успехом, и ни
        один замер досмотра сухим прогоном не доказывался.

        Мерка взята не своя, а та же, по которой показ отличает титры от аварии:
        :data:`torrcast.state.WATCHED_RATIO` (:meth:`torrcast.cli._Revival.resurrect`).
        Не дошли до неё - это обрыв, и дальше он проходит через терпение приёмника
        (:meth:`_wait`) ровно как оборванная картинка на ТВ.

        ⚠️ Длину фильма приёмник знает не всегда: ``report.duration`` набирает
        :meth:`_audit` по манифесту, и до первого его ответа там ноль. Судить не по чему -
        работает прежнее правило, иначе конец фильма не опознавался бы вовсе.
        """
        if self._proc is None or self._proc.poll() != 0:
            return False
        whole = self.report.duration
        return whole <= 0 or self._pos.pos >= whole * WATCHED_RATIO

    def _wait(self, pos: float) -> bool:
        """Терпение приёмника к стоящей картинке; ``False`` - оно кончилось, показ брошен.

        Внутри терпения приёмник пробует поднять себя сам - те самые два перезабора куска
        (:attr:`SEGMENT_RETRIES`), разнесённые по терпению поровну. Источник к этому моменту
        может уже вернуться, и тогда картинка пойдёт дальше без всякого воскрешения;
        а не вернулся - терпение выходит, и показ гаснет так же молча, как на ТВ.
        """
        now = self.clock.monotonic()
        self._still = self._still or now
        dark = now - self._still
        if dark >= self.patience:
            self._dead = True
            self._quiet()
            return False
        step = self.patience / (self.profile.segment_retries + 1)
        if self._loads < self.profile.segment_retries and dark >= step * (self._loads + 1):
            self._loads += 1
            with contextlib.suppress(InfraError, OSError):
                self._open(self._url, pos)  # источника всё ещё нет - терпим дальше
        return True

    def replay(self, at: float) -> float:
        """Поднять СВОЙ погасший показ с секунды ``at``; вернуть секунду, с которой он пошёл.

        Тот же договор, что и у :meth:`torrcast.cast.ChromecastReceiver.replay`: позиция
        приходит снаружи (у мёртвой сессии её нет), исключения наружу не выпускаются, а
        место подъёма называется только про действительно вернувшуюся картинку, а не про
        отправленный LOAD; ``0.0`` - её нет. Ждать её дольше :attr:`WAKE_TIMEOUT`
        незачем: попытка тут не одна.

        Своей сетки заглушка не знает и куски не перешагивает, поэтому пошла она ровно
        оттуда, откуда просили. Это и есть разница с живым приёмником, а не упрощение.

        ⚠️ Чужой показ заглушка не видит и видеть не может - :meth:`ChromecastReceiver._free`
        здесь не воспроизводится ничем. Что приёмник занят чужим, проверяется только на
        живом ТВ.
        """
        if not self._url or self.clock.monotonic() < self._sulk:
            return 0.0  # приёмник поймал 404 и ближайшие минуты не берёт LOAD вовсе
        try:
            self._open(self._url, at)
        except (InfraError, OSError):
            return 0.0  # источника всё ещё нет - зовущий попробует ещё раз или погасит
        self._seen, self._still, self._loads = at, 0.0, 0
        deadline = self.clock.monotonic() + self.WAKE_TIMEOUT
        while self.clock.monotonic() < deadline:
            self.clock.sleep(1.0)
            if self._pos.pos > at:  # декодер поехал - картинка на экране
                self._dead = False
                return at
            if not self._pos.playing:
                break  # декодер лёг, не начав: показа нет, и врать о нём нельзя
        self._quiet()
        return 0.0

    def _session(self) -> Any:
        import requests

        session = requests.Session()
        session.verify = self.ca or True
        return session

    def _probe(self, url: str) -> str:
        """Первый ответ раздачи: TLS, доступность, CORS. Манифест отдаётся зовущему -
        по нему :meth:`_from` и считает, с какого куска приёмник начнёт.
        """
        import requests

        try:
            response = self._session().get(url, timeout=30)
            self._caught(response)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise InfraError(f"приёмник не забрал манифест: {why(exc)}") from exc
        if response.headers.get(_CORS_HEADER) != "*":
            raise InfraError(f"в ответе нет {_CORS_HEADER}: * - Chromecast такое молча не играет")
        return str(response.text)  # сессия нетипизирована - тело забираем строкой явно

    def _follow(self, url: str) -> None:
        """Позиция из ``-progress`` декодера: ровно то, что ТВ отдал бы сторожу."""
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            if line.startswith("out_time_us="):
                with contextlib.suppress(ValueError):
                    # Позиция абсолютная, как у живого приёмника: показ мог начаться
                    # с середины фильма (resume), а декодер считает время от своего старта.
                    self._pos = Position(self._start + int(line[12:]) / 1e6, self._pos.dur, True)
        proc.wait()
        self._done.set()
        self.report.decoded = self._pos.pos
        err, self._err = self._err, None
        if err is not None:
            with err:
                err.seek(0)
                text = err.read().decode("utf-8", "replace")
            self.report.gaps += len(_LOST_RE.findall(text))
        self._pos = Position(self._pos.pos, self._pos.dur, False)

    def _audit(self, url: str) -> None:
        """Сегменты забираются по сети, как ТВ: HEAD на каждый — CORS, размер, нумерация.

        ⚠️ Идти по манифесту подряд и сразу нельзя: он описывает **весь фильм**, а файлы
        появляются там, где показ идёт прямо сейчас. Спросить всё разом —
        значит потребовать упаковать фильм целиком, чего tmpfs и не выдержит. Поэтому
        mock, как и живой приёмник, спрашивает только то, до чего дошёл декодер.

        🔴 Кусок, который КОНЧАЕТСЯ на месте захода, приёмнику не нужен: он весь позади.
        Строгое «кончился раньше» оставляло его в списке (на сетке по 10 с заход на 10.0 с
        честно спрашивал нулевой кусок), и раздача уходила паковать с нуля - тот самый
        лишний заход упаковки, ради которого декодеру срезают голову плейлиста
        (:meth:`_from`). Сравнение тут с тем же допуском: границы сетки складываются из
        округлённых ``EXTINF`` и на секунду захода бит в бит не ложатся.
        """
        session, base = self._session(), url.rsplit("/", 1)[0]
        try:
            body = session.get(url, timeout=30)
            self._check(body)
            segments, _ = parse_manifest(body.text)
        except Exception:  # без манифеста показа нет вовсе - это уже поймал _probe
            self._done.set()
            return
        self.report.duration = sum(seconds for _, seconds in segments)
        at = 0.0
        for name, seconds in segments:
            end = at + seconds
            at = end
            if end <= self._start + _GRID_SLACK:  # кусок весь позади захода - он не нужен
                continue
            while not self._done.is_set() and self._pos.pos + _AUDIT_AHEAD < end:
                self._done.wait(0.5)
            if self._done.is_set():
                return
            self.report.segments += 1
            number = _NUM_RE.search(name)
            if number and self._last >= 0 and int(number.group(1)) != self._last + 1:
                self.report.gaps += 1
            self._last = int(number.group(1)) if number else self._last
            self._measure(session, f"{base}/{name}", seconds)

    def _measure(self, session: Any, url: str, seconds: float) -> None:
        try:
            head = session.head(url, timeout=30)
            self._check(head)
            size = int(head.headers.get("Content-Length") or 0)
        except Exception:  # сегмент из манифеста обязан отдаваться - иначе это дыра
            self.report.gaps += 1
            return
        if seconds > 0:
            self.report.peak_mbit = max(self.report.peak_mbit, size * 8 / seconds / 1e6)

    def _check(self, response: Any) -> None:
        self._caught(response)
        response.raise_for_status()
        if response.headers.get(_CORS_HEADER) != "*":
            self.report.no_cors += 1

    def _caught(self, response: Any) -> None:
        """404 приёмник помнит :attr:`SULK` секунд - и это ноль (замер 09-08-2026).

        🔴 Наказание за 404 опровергнуто трижды на живом Q70D двумя независимыми
        каналами: LOAD после 404 берётся даже быстрее обычного тёплого. Поэтому заглушка
        за него больше и не наказывает - модель обязана держаться замера, а не легенды.

        ⚠️ Механизм оставлен на месте, и поле в профиле тоже: мерили мгновенный чистый
        404 внутри здоровой сессии, а прежнее наблюдение пришло из другого сценария.
        Найдётся приёмник, который обижается, - наказание вернётся числом в его профиле,
        а не правкой кода. И на решение «держать запрос вместо 404»
        (:attr:`torrcast.stream.Feed.wait`) этот ноль не влияет вовсе.
        """
        if getattr(response, "status_code", 0) == 404:
            self._sulk = self.clock.monotonic() + self.profile.sulk
