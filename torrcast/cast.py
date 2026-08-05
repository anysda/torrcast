"""Приёмники: реальный Chromecast и mock — интерфейс с двумя реализациями (§3 ТЗ).

``mock`` не заглушка «для галочки»: headless-клиент тянет манифест и сегменты тем же
транспортом, что и ТВ, проверяет CORS и непрерывность нумерации, декодирует ffmpeg'ом
и отдаёт позицию — на нём проходит вся автономная приёмка (§7, реестр ТВ-рисков §9).
Samsung-специфики здесь нет и быть не должно (§1): ни PowerState, ни nudge-сторожей.
"""

from __future__ import annotations

import contextlib
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import IO, Any, Literal, Protocol, runtime_checkable

from torrcast import InfraError, why
from torrcast.stream import parse_manifest

__all__ = [
    "HLS_HINTS",
    "HLS_TYPE",
    "ChromecastReceiver",
    "MockReceiver",
    "Position",
    "Receiver",
    "Report",
    "make_receiver",
    "trust_anchor",
]

ReceiverKind = Literal["chromecast", "mock"]

#: Тип манифеста и подсказки формата сегментов: без них Default Media Receiver
#: отвечает LOAD ERROR на муксованный TS (грабли kinocast на этом же Q70D).
HLS_TYPE = "application/vnd.apple.mpegurl"
HLS_HINTS = {"hlsVideoSegmentFormat": "mpeg2_ts", "hlsSegmentFormat": "ts"}

#: Номер сегмента в имени ``index<N>.ts`` — по нему ловятся дыры в нумерации.
_NUM_RE = re.compile(r"(\d+)\.ts$")
#: Строки ffmpeg, означающие, что кусок не доехал: для приёмки это разрыв.
_LOST_RE = re.compile(r"Failed to open segment|Error opening|Cannot reload|skipping", re.I)
_CORS_HEADER = "Access-Control-Allow-Origin"
#: На сколько секунд вперёд декодера mock позволяет себе спрашивать сегменты.
_AUDIT_AHEAD = 8.0


@dataclass(frozen=True, slots=True)
class Position:
    pos: float
    dur: float
    playing: bool = False
    #: Состояние приёмника как есть (``PLAYING``/``BUFFERING``/``PAUSED``/``IDLE``).
    #: Показу нужно отличать паузу на пульте от конца фильма: на паузе упаковка гасится,
    #: но показ жив и продолжится с того же места (§6 SPEC-v2).
    state: str = ""

    @property
    def ratio(self) -> float:
        return self.pos / self.dur if self.dur > 0 else 0.0


@runtime_checkable
class Receiver(Protocol):
    """Что нам нужно от приёмника — и ничего сверх того."""

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        """Начать воспроизведение HLS-манифеста с секунды ``at``."""

    def stop(self, quit_app: bool = False) -> None:
        """Снять каст; ``quit_app`` — ещё и закрыть приложение приёмника (§2.5 SPEC-v2).

        ``quit_app=False`` — показ передают дальше (стык серий): приложение остаётся
        открытым, следующая серия грузится в него же.
        """

    def position(self, front: float = 0.0) -> Position:
        """Текущая позиция и длительность; ``front`` — докуда упаковано (§6 SPEC-v2)."""


@dataclass(slots=True)
class Report:
    """Что mock увидел как приёмник — цифры приёмки §7.2."""

    segments: int = 0
    duration: float = 0.0
    decoded: float = 0.0
    gaps: int = 0
    peak_mbit: float = 0.0
    #: Ответы без ``Access-Control-Allow-Origin``: Chromecast на таких молча молчит (§9).
    no_cors: int = 0

    @property
    def ok(self) -> bool:
        """Приёмка §7.2: дыр нет, CORS везде, декодировано до конца (хвост в один сегмент)."""
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


class ChromecastReceiver:
    """Реальный приёмник: pychromecast по адресу из конфига.

    Почему не catt: его ``cast <url>`` гонит любой URL через yt-dlp и не умеет передать
    подсказки формата HLS (:data:`HLS_HINTS`), без которых ресивер отвечает LOAD ERROR.
    ⚠️ Порт 8009 открыт даже в standby, любой коннект будит ТВ (§8) — поэтому соединение
    поднимается лениво, только когда кастить действительно собираются, а до этапа 6
    адрес ТВ в конфиге отсутствует физически.

    ⚠️ **Сендер к приёмнику должен быть ровно один.** У всех соединений pychromecast
    ``source_id`` один и тот же — ``sender-0`` (socket_client.py), поэтому второй процесс,
    подключившийся к тому же ТВ, для приёмника неотличим от первого. Ломается это так:
    показ идёт (ТВ качает сегменты и рисует картинку), а владеющий сессией процесс
    получает на ``GET_STATUS`` пустой ``MEDIA_STATUS`` — то есть вечный ``IDLE`` при
    ``app_id=CC1AD845`` и живом ``status_text``. Дальше сторож честно решает, что LOAD не
    взяли, закрывает приложение и в итоге гасит показ. Замерено 05-08-2026: три прогона
    подряд умерли ровно так, и каждый раз рядом был чужой сендер — пробоотборник,
    диагностический скрипт или их ``quit_app`` минутой раньше. Отсюда правило для
    диагностики: наблюдать за показом можно чем угодно, кроме второго pychromecast —
    позиция и так лежит в state.json, а забор сегментов виден в ``ss``.
    """

    #: Пока показ ни разу не начался, ``IDLE`` — это «ещё грузится», а не отказ: ресивер
    #: сначала тянет манифест и первый сегмент, и до этого статус остаётся IDLE. Замерено
    #: на живом Q70D 05-08-2026: ``play_media`` возвращается через 0.03 с, а PLAYING
    #: приходит через 0.7–1.5 с — то есть «сразу после LOAD» приёмник всегда не играет.
    START_TIMEOUT = 90.0
    #: Сколько ждём картинку, когда показ **возобновляют** (перепаковка после перемотки
    #: назад за окно, возврат с паузы). ⚠️ Ресивер, поймавший 404 на пропавшем сегменте,
    #: не берёт LOAD ещё пару минут — замерено 05-08-2026: ни повтор LOAD, ни `quit_app`,
    #: ни новое соединение, ни новый процесс не ускоряют это ни на секунду, а вот через
    #: 2.5–3 минуты он снова играет с первой попытки. Поэтому здесь не 90 с, а терпение:
    #: показ возвращается сам, вместо того чтобы умереть у человека на глазах.
    REVIVE_TIMEOUT = 300.0
    #: Как часто повторять LOAD, пока приёмник не берёт его.
    LOAD_RETRIES = 2
    #: Пауза между повторами LOAD: ресиверу нужно время закрыть прошлую сессию.
    LOAD_PAUSE = 3.0
    #: Столько терпим молчаливый IDLE после LOAD, прежде чем считать, что его не взяли.
    #: ⚠️ Это не противоречит «IDLE до первого показа — это загрузка»: живой Q70D отвечает
    #: PLAYING за 0.7–1.5 с, а 30 с молчания означают, что грузить он не начинал.
    STUCK_SECONDS = 30.0
    #: app_id Default Media Receiver: чужой app = каст сняли пультом, показ окончен.
    MEDIA_APP = "CC1AD845"
    #: Неподвижный BUFFERING дольше этого — приёмник завис (см. :meth:`_nudge`).
    #: Штатный ребуфер на живом Q70D укладывается в 1–3 с, так что 8 с — это уже не он.
    #: ⚠️ Мелкий порог был бы опасен, пока «завис» и «ждёт упаковку» не различались: с
    #: упаковкой по требованию (§2.1 SPEC-v2) законный BUFFERING в неупакованном месте
    #: длится секунды, и нудж на нём мешал бы нам самим. Теперь их различает ``front``
    #: (см. :attr:`READY_AHEAD`), и терпеть зависание сорок пять секунд больше незачем:
    #: замерено 05-08-2026 — приёмник встал на 1:24 «Моаны» при 60 с готового запаса и
    #: сам не ожил ни разу, а весь провал показа был ровно порогом этого сторожа.
    STALL_SECONDS = 8.0
    #: Столько секунд упаковки впереди позиции считаем доказательством «еда на столе».
    #: Меньше — приёмник ждёт нас, и лечится это упаковкой, а не перемоткой.
    READY_AHEAD = 8.0
    #: Шаг прыжка вперёд на каждом нудже: мимо куска, на котором приёмник споткнулся.
    STALL_SKIP = 8.0

    def __init__(self, address: str) -> None:
        if not address:
            raise InfraError("адрес ТВ не задан: cast --tv <ip>")
        self.address = address
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

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        """Начать показ с секунды ``at`` и **дождаться картинки**, а не просто отправить LOAD.

        Без ожидания показ гаснет через секунду после команды: сторож снимает позицию
        сразу после ``play_media``, видит закономерный IDLE и считает, что играть нечего.

        ``at`` — это resume (§2.3): манифест описывает весь фильм, поэтому продолжение с
        середины делается не перепаковкой «с нуля потока», а обычным LOAD с позицией.

        Зовётся один раз за показ. Перемотка сюда больше не приходит: приёмник видит весь
        фильм и мотает сам, а упаковка идёт следом за его запросами (§2.1 SPEC-v2).
        """
        self._url, self._title = url, title or "torrcast"
        self._peak, self._reloads, self._stall_hits = at, 0, 0
        self._stall_at, self._stall_since = -1.0, 0.0
        budget = self.REVIVE_TIMEOUT if self._started else self.START_TIMEOUT
        self._started = True
        self._at = at
        self._load(at)
        if self._settle(budget):
            return
        raise InfraError(f"ТВ {self.address} не начал показ: {self._why()}")

    def stop(self, quit_app: bool = False) -> None:
        """Снять каст, а по ``quit_app`` — ещё и закрыть приложение приёмника.

        Зачем закрывать: ``media_controller.stop()`` гасит только показ, а Default Media
        Receiver остаётся на экране иконкой и висит там до собственного таймаута простоя —
        владелец видит её после `cast stop` и после титров, и она же оттягивает
        автовыключение ТВ. ``quit_app`` возвращает телевизор в исходное состояние
        (``app_id`` пустеет либо становится Backdrop) сразу.

        ⚠️ Закрываем **только свою** сессию (:meth:`_ours`): на этом же ТВ живут kinocast
        и castbot, и они кастят через тот же Default Media Receiver. Чужой показ снимать
        нельзя — ни ``stop``, ни тем более ``quit_app``.

        Соединение после закрытия рвём сами: сендер, переживший своё приложение, для
        следующего показа — тот самый «второй pychromecast», из-за которого приёмник
        отдаёт пустой MEDIA_STATUS (см. предупреждение в докстринге класса).
        """
        if self._cast is None or not self._ours():
            return
        with contextlib.suppress(Exception):
            self._cast.media_controller.stop()
        if not quit_app:
            return  # показ передают следующей серии — приложение ей и достанется
        with contextlib.suppress(Exception):
            self._cast.quit_app()
        with contextlib.suppress(Exception):
            self._cast.disconnect()
        self._cast, self._session = None, ""

    def _ours(self) -> bool:
        """Наша ли сессия сейчас на приёмнике — по трём признакам подряд.

        ⚠️ Статус берётся **кэшированный**: ``update_status`` на закрытом приёмнике
        поднимает пустой Default Media Receiver обратно (грабли kinocast, см.
        :meth:`_status`), а нам здесь именно закрывать. Кэш держится свежим сам:
        приёмник шлёт ``RECEIVER_STATUS`` в наш живой сокет на каждое изменение.

        * приложение не наше (``app_id`` пустой или чужой) — трогать нечего;
        * приложение то же, но сессию поднял кто-то другой — это чужой показ;
        * сессия та же, но играет не наш URL — значит, в наше приложение загрузился
          другой сендер (kinocast/castbot делают ровно это, ``session_id`` при этом
          не меняется).
        """
        status = getattr(self._cast, "status", None)
        if getattr(status, "app_id", None) != self.MEDIA_APP:
            return False
        session = getattr(status, "session_id", "") or ""
        if self._session and session and session != self._session:
            return False
        playing = getattr(self._cast.media_controller.status, "content_id", "") or ""
        return not playing or not self._url or playing == self._url

    def position(self, front: float = 0.0) -> Position:
        st = self._status()
        state = str(st.player_state or "")
        pos = st.current_time or 0.0
        if pos > self._peak:  # реальный прогресс — прошлые нуджи больше не в счёт
            self._peak, self._stall_hits = pos, 0
        if state == "BUFFERING":
            self._nudge(pos, front)
        else:
            self._stall_at, self._stall_since = -1.0, 0.0
        if state == "IDLE" and st.idle_reason == "ERROR" and self._reload():
            return Position(self._peak, st.duration or 0.0, True, "BUFFERING")
        return Position(pos, st.duration or 0.0, st.player_is_playing, state)

    def _reload(self) -> bool:
        """Повтор LOAD посреди показа: приёмник отвалился с ``IDLE/ERROR``.

        Рецептура kinocast на этом же ТВ: ровно две попытки, дальше это не наша авария.
        Грузим с ``current_time``: манифест описывает весь фильм, поэтому вернуть
        приёмник ровно туда, где он споткнулся, — это просто позиция в LOAD.
        """
        if self._reloads >= self.LOAD_RETRIES:
            return False
        self._reloads += 1
        print(f"приёмник отвалился на {self._peak:.0f} с — повтор LOAD", flush=True)
        try:
            self._restart_app()  # чистое приложение: залипший молчит на любой LOAD
            self._load(self._peak)
        except Exception:  # приёмник мог просто уйти — решает следующий тик
            return False
        return True

    def _nudge(self, pos: float, front: float = 0.0) -> None:
        """Расшевелить приёмник, зависший в BUFFERING на одной и той же секунде.

        Расшевеливать имеет смысл, только когда еда на столе: ``front`` — докуда упаковано,
        и пока запас впереди позиции меньше :attr:`READY_AHEAD`, приёмник ждёт **нас**, а
        не завис. Такой BUFFERING лечится упаковкой, и прыгать по нему нельзя: прыгнешь —
        уедешь в неупакованное место и заставишь раздачу паковать заново.

        Замерено на живом Q70D 05-08-2026: на 273-й секунде показа ресивер перестал
        запрашивать сегменты и встал в BUFFERING **навсегда** — при том что следующий
        кусок лежал в tmpfs и отдавался curl'ом за миллисекунды, а живого соединения от ТВ
        в conntrack не было вовсе. То есть подвисает сам приёмник, и лечится это ``seek``:
        показ возобновляется немедленно. Тот же сторож годами держит kinocast на этом ТВ.

        ⚠️ Прыгать можно **только вперёд**, и целиться — от пройденного максимума.
        На растущем манифесте ресивер отрабатывал ``seek`` не точно, а с начала
        подходящего сегмента, и «нудж на месте» откатывал показ на ~35 с назад: позиция
        после отката меньше максимума, счётчик не сбрасывался — и получалась бесконечная
        лесенка назад (наблюдалась живьём: 2:12 → 1:58 → 1:44). С манифестом на весь
        фильм ``seek`` стал точным (замерено: позиция встаёт ровно в запрошенную), но
        правило остаётся: нудж — это лечение застрявшего куска, и лечится он тем, что
        кусок пропускают, а не тем, что его переигрывают.
        """
        now = time.monotonic()
        if pos != self._stall_at:
            self._stall_at, self._stall_since = pos, now
            return
        if now - self._stall_since < self.STALL_SECONDS:
            return
        if front - pos < self.READY_AHEAD:
            return  # приёмник ждёт упаковку — это наша забота, а не его зависание
        self._stall_hits += 1
        self._stall_since = now
        with contextlib.suppress(Exception):
            self._device().media_controller.seek(self._peak + self.STALL_SKIP * self._stall_hits)

    def _load(self, at: float = 0.0) -> None:
        controller = self._device().media_controller
        # BUFFERED, а не LIVE: манифест VOD знает длительность целиком, и ресивер
        # рисует шкалу с общим временем — перемотка пультом работает (§2.1 SPEC-v2).
        controller.play_media(
            self._url,
            HLS_TYPE,
            title=self._title,
            stream_type="BUFFERED",
            media_info=HLS_HINTS,
            current_time=at,
        )
        controller.block_until_active(timeout=30)
        # Чья сессия на приёмнике — запоминаем здесь: по ней :meth:`_ours` отличит наш
        # показ от чужого, когда придёт пора закрывать приложение.
        self._session = getattr(self._cast.status, "session_id", "") or ""

    def _settle(self, budget: float) -> bool:
        """Дождаться, пока приёмник действительно заиграет; отказ LOAD — повторить LOAD.

        ``IDLE`` без причины — это «ещё грузится», его терпим до :data:`START_TIMEOUT`.
        А вот причина говорит, что LOAD не взяли, и ждать бессмысленно:

        * ``ERROR`` — ресивер не смог начать (рецепт kinocast: ровно 2 попытки);
        * ``IDLE`` дольше :data:`STUCK_SECONDS` — LOAD не взяли молча. Такое поймано
          05-08-2026 после перепаковки: приёмник стоял в IDLE при живых сегментах.

        Пробуем до конца ``budget``, а не «два раза»: приёмник после 404 оживает минутами,
        и единственное, что работает, — терпеливо повторять LOAD.

        ⚠️ ``INTERRUPTED`` поводом для повтора НЕ является: так ресивер отчитывается о
        КОНЦЕ ПРЕЖНЕЙ сессии, которую оборвал наш же новый LOAD. Повтор на него сбивает
        только что принятый LOAD — проверено живьём, показ на этом и умер.

        Любая повторная попытка идёт в чистое приложение: залипший Default Media Receiver
        молчит на все LOAD подряд, а `quit_app` лечит сразу.
        """
        deadline = time.monotonic() + budget
        tried = time.monotonic()
        while time.monotonic() < deadline:
            time.sleep(1.0)
            status = self._status()
            if status.player_state in ("PLAYING", "BUFFERING"):
                return True
            waited = time.monotonic() - tried
            refused = status.idle_reason == "ERROR" and waited >= self.LOAD_PAUSE
            if refused or waited >= self.STUCK_SECONDS:
                self._reloads += 1
                tried = time.monotonic()
                left = deadline - time.monotonic()
                print(f"LOAD не взяли ({self._why()}) — гружу заново, ещё {left:.0f} с", flush=True)
                self._restart_app()
                self._load(self._at)
        return False

    def _restart_app(self) -> None:
        """Закрыть приложение приёмника **и своё соединение** — следующий LOAD уходит в
        чистое с обеих сторон.

        ⚠️ Одного `quit_app` мало, замерено 05-08-2026 трижды подряд: приложение честно
        закрывается (``app_id`` становится ``None``), следующий LOAD по ТОМУ ЖЕ сокету
        поднимает его обратно — и показ не начинается, приёмник стоит в IDLE до самой
        смерти юнита. При этом новый процесс с новым соединением на том же ТВ поднимает
        картинку за 3 с. Значит, чинить надо не только приёмник, но и свою сессию.
        """
        print("приёмник залип — закрываю приложение и соединение, гружу заново", flush=True)
        if self._cast is not None:
            with contextlib.suppress(Exception):
                self._cast.quit_app()
            with contextlib.suppress(Exception):
                self._cast.disconnect()
        self._cast = None  # следующий _device() поднимет соединение заново
        time.sleep(self.LOAD_PAUSE)

    def _status(self) -> Any:
        """Свежий статус приёмника. ``update_status`` обязателен: без него pychromecast
        отдаёт последний присланный статус, и позиция замирает навсегда — сторож считает,
        что показ стоит, окно сегментов не чистится и tmpfs растёт до конца фильма.
        """
        controller = self._device().media_controller
        # ⚠️ На закрытом ресивере update_status ПЕРЕЗАПУСКАЕТ пустой Default Media
        # Receiver — «вышел в Home, а каст открылся снова» (грабли kinocast). Поэтому
        # чужой app_id проверяем раньше и статус не трогаем.
        if getattr(self._cast.status, "app_id", None) != self.MEDIA_APP:
            return controller.status
        with contextlib.suppress(Exception):
            controller.update_status()
        return controller.status

    def _why(self) -> str:
        status = self._status()
        state = status.player_state or "нет статуса"
        return f"{state}/{status.idle_reason}" if status.idle_reason else str(state)

    def _device(self) -> Any:
        if self._cast is None:
            import uuid

            import pychromecast

            try:
                device = pychromecast.get_chromecast_from_host(
                    (self.address, 8009, uuid.UUID(int=0), None, None), timeout=10
                )
                device.wait(timeout=20)
            except Exception as exc:
                raise InfraError(f"ТВ {self.address} не принял каст: {why(exc)}") from exc
            self._cast = device
        return self._cast


class MockReceiver:
    """Headless-приёмник: тянет HLS ровно как ТВ и декодирует ffmpeg'ом в ``/dev/null``.

    Адрес приходит готовым, и по нему же выбирается строгость: на https TLS проверяется
    по-настоящему, а не ``verify=False`` — чему доверять, решает :func:`trust_anchor`
    (системное хранилище для настоящего LE-серта, ровно как у ТВ, или сам файл для
    self-signed; пустой ``ca`` = хранилище, §9). На http проверять нечего.
    """

    def __init__(self, ca: str = "") -> None:
        self.ca = ca
        self.report = Report()
        self._proc: subprocess.Popen[str] | None = None
        self._err: IO[bytes] | None = None
        self._pos = Position(0.0, 0.0, False)
        self._done = threading.Event()
        self._start = 0.0
        self._last = -1

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        self._probe(url)  # первый ответ проверяем сами: TLS, доступность, CORS
        self._err = tempfile.TemporaryFile()  # noqa: SIM115 — живёт всё воспроизведение
        self._start = at
        # ⚠️ Опции TLS ставятся только под https-адрес: на http ffmpeg не «игнорирует
        # лишнее», а падает с «Option tls_verify not found» ещё до открытия входа —
        # то есть на дефолтном транспорте (§5 SPEC-v2) mock не декодировал бы ничего.
        tls = ["-tls_verify", "1", *(["-ca_file", self.ca] if self.ca else [])]
        command = [
            "ffmpeg", "-hide_banner", "-nostats", "-loglevel", "warning",
            *(tls if url.startswith("https://") else []),
            *(["-ss", f"{at:.3f}"] if at > 0 else []),
            "-i", url, "-progress", "pipe:1", "-f", "null", "-",
        ]  # fmt: skip
        try:
            self._proc = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=self._err, text=True
            )
        except FileNotFoundError as exc:
            raise InfraError("ffmpeg не установлен") from exc
        self._pos = Position(0.0, 0.0, True)
        for target in (self._follow, self._audit):
            threading.Thread(target=target, args=(url,), daemon=True).start()

    def stop(self, quit_app: bool = False) -> None:
        """Снять каст. Приложения у mock нет, поэтому ``quit_app`` ему нечего закрывать —
        аргумент есть только затем, чтобы mock оставался приёмником (:class:`Receiver`).
        """
        self._done.set()
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._proc.wait(timeout=5)
        self._pos = Position(self._pos.pos, self._pos.dur, False)

    def position(self, front: float = 0.0) -> Position:
        # dur — то, что уже упаковано и лежит в манифесте: показ по нему видит, насколько
        # упаковка ушла вперёд от приёмника. Запас mock'у ни к чему: он не зависает.
        playing = self._pos.playing
        return Position(self._pos.pos, self.report.duration, playing, "PLAYING" if playing else "")

    def _session(self) -> Any:
        import requests

        session = requests.Session()
        session.verify = self.ca or True
        return session

    def _probe(self, url: str) -> None:
        import requests

        try:
            response = self._session().get(url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise InfraError(f"приёмник не забрал манифест: {why(exc)}") from exc
        if response.headers.get(_CORS_HEADER) != "*":
            raise InfraError(f"в ответе нет {_CORS_HEADER}: * — Chromecast такое молча не играет")

    def _follow(self, url: str) -> None:
        """Позиция из ``-progress`` декодера: ровно то, что ТВ отдал бы сторожу (§2.5)."""
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
        if self._err is not None:
            self._err.seek(0)
            text = self._err.read().decode("utf-8", "replace")
            self.report.gaps += len(_LOST_RE.findall(text))
        self._pos = Position(self._pos.pos, self._pos.dur, False)

    def _audit(self, url: str) -> None:
        """Сегменты забираются по сети, как ТВ: HEAD на каждый — CORS, размер, нумерация.

        ⚠️ Идти по манифесту подряд и сразу нельзя: он описывает **весь фильм**, а файлы
        появляются там, где показ идёт прямо сейчас (§2.1 SPEC-v2). Спросить всё разом —
        значит потребовать упаковать фильм целиком, чего tmpfs и не выдержит. Поэтому
        mock, как и живой приёмник, спрашивает только то, до чего дошёл декодер.
        """
        session, base = self._session(), url.rsplit("/", 1)[0]
        try:
            body = session.get(url, timeout=30)
            self._check(body)
            segments, _ = parse_manifest(body.text)
        except Exception:  # без манифеста показа нет вовсе — это уже поймал _probe
            self._done.set()
            return
        self.report.duration = sum(seconds for _, seconds in segments)
        at = 0.0
        for name, seconds in segments:
            end = at + seconds
            at = end
            if end < self._start:  # до этого места показ и не доходил
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
        except Exception:  # сегмент из манифеста обязан отдаваться — иначе это дыра
            self.report.gaps += 1
            return
        if seconds > 0:
            self.report.peak_mbit = max(self.report.peak_mbit, size * 8 / seconds / 1e6)

    def _check(self, response: Any) -> None:
        response.raise_for_status()
        if response.headers.get(_CORS_HEADER) != "*":
            self.report.no_cors += 1


def trust_anchor(cert: str) -> str:
    """Чему приёмник должен доверять, проверяя нашу раздачу.

    Серт выпущен настоящим CA (LE на стенде) — доверяем **системному хранилищу**: ровно
    так его проверит ТВ, и только такая проверка закрывает риск §9 «Chromecast требует
    доверенный HTTPS». Серт self-signed (дефолт `install.sh` до доставки LE) — доверяем
    ему самому: иначе проверять нечем.

    Различаем по файлу: OpenSSL берёт в доверенные только CA-сертификаты, поэтому у
    self-signed остаётся он сам (subject == issuer), а у цепочки LE — промежуточный
    (subject != issuer), листа в списке нет вовсе.
    """
    import ssl

    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=cert)
        anchors = context.get_ca_certs()
    except (OSError, ssl.SSLError):
        return cert  # нечитаемый серт — пусть падает там, где это видно
    if len(anchors) == 1 and anchors[0].get("subject") == anchors[0].get("issuer"):
        return cert
    return ""


def make_receiver(kind: ReceiverKind, address: str = "", ca: str = "") -> Receiver:
    if kind == "mock":
        return MockReceiver(trust_anchor(ca) if ca else "")
    return ChromecastReceiver(address)
