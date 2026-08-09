"""Приёмники: реальный Chromecast и mock — интерфейс с двумя реализациями.

``mock`` не заглушка «для галочки»: headless-клиент тянет манифест и сегменты тем же
транспортом, что и ТВ, проверяет CORS и непрерывность нумерации, декодирует ffmpeg'ом
и отдаёт позицию. На нём проходит автономная приёмка ТРАНСПОРТА и ДЕКОДА, но не всего
показа: mock проигрывает фильм за секунды стенных часов, а не в реальном темпе, и вторая
голова чтения - прогрев фильма на диск (:mod:`torrcast.warm`) - под ним не появляется
вовсе. Значит зелёный сухой прогон доказывает раздачу и декод, но НЕ прогрев; сам прогрев
проверяется отдельно (tests/test_warm.py, живой ТВ). Подробности - в докстринге
:class:`MockReceiver`.

⚠️ Повадки конкретных приёмников тут ЕСТЬ, и утверждать обратное (прежняя строка гласила
«Samsung-специфики здесь нет и быть не должно») - врать: в модуле живёт и сторож подвиса
с порогами, снятыми с Samsung Q70D (:meth:`ChromecastReceiver._nudge`), и терпение к
пустому экрану, и число перезаборов куска. Правило другое и выполнимое: ни одно из этих
чисел не прибито здесь константой - все они приходят из профиля приёмника
(:mod:`torrcast.profile`), а константы класса остаются умолчанием осторожного профиля.
"""

from __future__ import annotations

import contextlib
import logging
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import IO, Any, Literal, Protocol, runtime_checkable

from torrcast import InfraError, trace, why
from torrcast.profile import CAUTIOUS, Profile
from torrcast.stream import parse_manifest
from torrcast.timing import CLOCK, Clock

__all__ = [
    "HLS_HINTS",
    "HLS_TYPE",
    "ChromecastReceiver",
    "MockReceiver",
    "Position",
    "Receiver",
    "Report",
    "hush_cosmetic_noise",
    "make_receiver",
    "trust_anchor",
]

ReceiverKind = Literal["chromecast", "mock"]

#: Тип манифеста и подсказки формата сегментов: без них Default Media Receiver
#: отвечает LOAD ERROR на муксованный TS (известная особенность этого же Q70D).
HLS_TYPE = "application/vnd.apple.mpegurl"
HLS_HINTS = {"hlsVideoSegmentFormat": "mpeg2_ts", "hlsSegmentFormat": "ts"}

#: Номер сегмента в имени ``index<N>.ts`` - по нему ловятся дыры в нумерации.
_NUM_RE = re.compile(r"(\d+)\.ts$")
#: Строки ffmpeg, означающие, что кусок не доехал: для приёмки это разрыв.
_LOST_RE = re.compile(r"Failed to open segment|Error opening|Cannot reload|skipping", re.I)
_CORS_HEADER = "Access-Control-Allow-Origin"
#: На сколько секунд вперёд декодера mock позволяет себе спрашивать сегменты.
_AUDIT_AHEAD = 8.0

#: Логгер pychromecast, на котором живёт единственная приглушаемая строка (:class:`_Cosmetic`).
_DIAL_LOGGER = "pychromecast.dial"


class _Cosmetic(logging.Filter):
    """Гасит РОВНО одну строку pychromecast - косметическую, и ничего кроме неё.

    Строка: ``Failed to determine cast type for host ... (Connection refused) (services:...)``,
    и печатается она на КАЖДОМ подключении к приёмнику. Что за ней стоит: разбирая
    устройство, pychromecast спрашивает у него страницу сведений ``/setup/eureka_info``
    по https на порту 8443; у телевизора этого порта нет вовсе (8008 и 8009 открыты, 8443
    отвечает отказом), исключение ловится тут же на месте и подменяется типом устройства
    по умолчанию - на показ это не влияет ничем. ``port=8009`` внутри текста сбивает с
    толку отдельно: это распечатка списка сервисов устройства, а не отказавший порт.
    Строка уже стоила ложной гипотезы «телевизор выпадает по 8009», поэтому её и убираем.

    ⚠️ Глушится именно ОДНО сообщение, а не логгер: настоящие жалобы pychromecast должны
    доходить до человека. Чужая библиотека при этом не трогается - фильтр вешается
    снаружи, на её логгер (:func:`hush_cosmetic_noise`).
    """

    #: Начало шаблона сообщения; шаблон, а не готовый текст - фильтр стоит на логгере и
    #: видит запись до подстановки адреса и причины.
    NOISE = "Failed to determine cast type"

    def filter(self, record: logging.LogRecord) -> bool:
        return not str(record.msg).startswith(self.NOISE)


def hush_cosmetic_noise() -> None:
    """Повесить :class:`_Cosmetic` на логгер pychromecast; звать можно сколько угодно.

    Зовётся отовсюду, где поднимается pychromecast: и перед показом
    (:meth:`ChromecastReceiver._device`), и при поиске приёмников (:mod:`torrcast.scan`).
    """
    logger = logging.getLogger(_DIAL_LOGGER)
    if not any(isinstance(one, _Cosmetic) for one in logger.filters):
        logger.addFilter(_Cosmetic())


@dataclass(frozen=True, slots=True)
class Position:
    pos: float
    dur: float
    playing: bool = False
    #: Состояние приёмника как есть (``PLAYING``/``BUFFERING``/``PAUSED``/``IDLE``).
    #: Показу нужно отличать паузу на пульте от конца фильма: на паузе упаковка гасится,
    #: но показ жив и продолжится с того же места.
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
        """Снять каст; ``quit_app`` — ещё и закрыть приложение приёмника.

        ``quit_app=False`` — показ передают дальше (стык серий): приложение остаётся
        открытым, следующая серия грузится в него же.
        """

    def position(self, front: float = 0.0) -> Position:
        """Текущая позиция и длительность; ``front`` — докуда упаковано."""


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


class ChromecastReceiver:
    """Реальный приёмник: pychromecast по адресу из конфига.

    Почему не catt: его ``cast <url>`` гонит любой URL через yt-dlp и не умеет передать
    подсказки формата HLS (:data:`HLS_HINTS`), без которых ресивер отвечает LOAD ERROR.
    ⚠️ Порт 8009 открыт даже в standby, любой коннект будит ТВ — поэтому соединение
    поднимается лениво, только когда кастить действительно собираются.

    ⚠️ **Сендер к приёмнику должен быть ровно один.** У всех соединений pychromecast
    ``source_id`` один и тот же — ``sender-0`` (socket_client.py), поэтому второй процесс,
    подключившийся к тому же ТВ, для приёмника неотличим от первого. Ломается это так:
    показ идёт (ТВ качает сегменты и рисует картинку), а владеющий сессией процесс
    получает на ``GET_STATUS`` пустой ``MEDIA_STATUS`` — то есть вечный ``IDLE`` при
    ``app_id=CC1AD845`` и живом ``status_text``. Дальше сторож честно решает, что LOAD не
    взяли, закрывает приложение и в итоге гасит показ. Замерено: три прогона
    подряд умерли ровно так, и каждый раз рядом был чужой сендер — пробоотборник,
    диагностический скрипт или их ``quit_app`` минутой раньше. Отсюда правило для
    диагностики: наблюдать за показом можно чем угодно, кроме второго pychromecast —
    позиция и так лежит в state.json, а забор сегментов виден в ``ss``.
    """

    #: Пока показ ни разу не начался, ``IDLE`` - это «ещё грузится», а не отказ: ресивер
    #: сначала тянет манифест и первый сегмент, и до этого статус остаётся IDLE. Замерено
    #: на живом Q70D: ``play_media`` возвращается через 0.03 с, а PLAYING
    #: приходит через 0.7-1.5 с - то есть «сразу после LOAD» приёмник всегда не играет.
    START_TIMEOUT = 90.0
    #: Сколько ждём картинку, когда показ **возобновляют** (перепаковка после перемотки
    #: назад за окно, возврат с паузы).
    #:
    #: ⚠️ Прежнее объяснение («ресивер, поймавший 404, не берёт LOAD ещё пару минут»)
    #: замером 09-08-2026 опровергнуто трижды: наказания за 404 нет вовсе, ноль секунд
    #: (:attr:`torrcast.profile.Profile.sulk`), и LOAD после 404 берётся даже быстрее
    #: обычного тёплого - 3.2-3.6 с против 5.6 с. Число осталось прежним, но стоит оно
    #: теперь на другом замере: приложение Samsung Q70D висит на экране 301 с после
    #: смерти медиасессии (:attr:`torrcast.profile.Profile.app_patience`), и пять минут -
    #: это ровно окно, в котором показ ещё может вернуться в своё же приложение.
    #: Поэтому здесь не 90 с, а терпение: показ возвращается сам, вместо того чтобы
    #: умереть у человека на глазах.
    #: 🔴 Это число и соседние - **осторожный профиль** (:data:`torrcast.profile.CAUTIOUS`),
    #: и живут они здесь только умолчанием: живой показ берёт пороги из профиля своего
    #: приёмника (``self.profile``), а у приставки Android TV терпение к темноте и обида
    #: на 404 измерены совсем другими.
    REVIVE_TIMEOUT = CAUTIOUS.revive_timeout
    #: Сколько ждём картинку, поднимая ПОГАСШИЙ показ (:meth:`replay`). Здесь не 300 с:
    #: попытка тут не одна, интервалы держит зовущий (:class:`torrcast.cli._Revival`), и
    #: висеть в одной попытке пять минут значило бы проспать вернувшуюся сеть. Минуты
    #: хватает с запасом: живой Q70D отвечает PLAYING за 0.7-1.5 с, а внутри этого
    #: бюджета :meth:`_settle` успевает ещё раз перегрузить молчащий LOAD.
    WAKE_TIMEOUT = 60.0
    #: Как часто повторять LOAD, пока приёмник не берёт его.
    LOAD_RETRIES = CAUTIOUS.load_retries
    #: Пауза между повторами LOAD: ресиверу нужно время закрыть прошлую сессию.
    LOAD_PAUSE = 3.0
    #: Столько терпим молчаливый IDLE после LOAD, прежде чем считать, что его не взяли.
    #: ⚠️ Это не противоречит «IDLE до первого показа - это загрузка»: живой Q70D отвечает
    #: PLAYING за 0.7-1.5 с, а 30 с молчания означают, что грузить он не начинал.
    STUCK_SECONDS = 30.0
    #: app_id Default Media Receiver: чужой app = каст сняли пультом, показ окончен.
    MEDIA_APP = "CC1AD845"
    #: app_id заставки приёмника: показа на экране нет вовсе, приёмник ничем не занят.
    BACKDROP_APP = "E8C28D3C"
    #: Неподвижный BUFFERING дольше этого - приёмник завис (см. :meth:`_nudge`).
    #: Штатный ребуфер на живом Q70D укладывается в 1-3 с, так что 8 с - это уже не он.
    #: ⚠️ Мелкий порог был бы опасен, пока «завис» и «ждёт упаковку» не различались: с
    #: упаковкой по требованию законный BUFFERING в неупакованном месте
    #: длится секунды, и нудж на нём мешал бы нам самим. Теперь их различает ``front``
    #: (см. :attr:`READY_AHEAD`), и терпеть зависание сорок пять секунд больше незачем:
    #: замерено - приёмник встал на 1:24 «Моаны» при 60 с готового запаса и
    #: сам не ожил ни разу, а весь провал показа был ровно порогом этого сторожа.
    STALL_SECONDS = CAUTIOUS.stall_seconds
    #: Столько секунд упаковки впереди позиции считаем доказательством «еда на столе».
    #: Меньше - приёмник ждёт нас, и лечится это упаковкой, а не перемоткой.
    READY_AHEAD = CAUTIOUS.ready_ahead
    #: Шаг прыжка вперёд на каждом нудже: мимо куска, на котором приёмник споткнулся.
    STALL_SKIP = CAUTIOUS.stall_skip
    #: Столько нуджей подряд без единого показанного кадра - и сторож умолкает
    #: (:meth:`_nudge`, :attr:`torrcast.profile.Profile.blind_nudges`).
    BLIND_NUDGES = CAUTIOUS.blind_nudges
    #: Насколько позиция должна уехать назад, чтобы считать это перемоткой человека, а не
    #: дрожанием счётчика. Больше сегмента (:data:`torrcast.stream.Config.hls_segment` - 10 с
    #: по умолчанию) брать нельзя: перемотка на один кусок назад - обычное дело, и «максимум»
    #: после неё обязан опуститься. Меньше шага нуджа - тоже: свой же прыжок вперёд мы
    #: перемоткой назад считать не должны.
    REWIND = 8.0
    #: Насколько позиция должна прыгнуть между опросами, чтобы это была перемотка, а не ход
    #: показа. Опрос идёт раз в 2 с (:func:`torrcast.cli._hold`), и за него живой показ
    #: уходит на те же 2 с; берём с запасом на подвисший опрос. Собственный нудж под этот
    #: порог тоже попадает, поэтому он помечается отдельно (:attr:`_nudged_to`).
    SEEK_JUMP = 15.0

    def __init__(self, address: str, profile: Profile = CAUTIOUS) -> None:
        if not address:
            raise InfraError("адрес ТВ не задан: cast --tv - найдёт телевизоры в сети")
        self.address = address
        #: Профиль этого приёмника: его терпение, его повторы LOAD, его сторож нуджей.
        #: Умолчание осторожное - показ без выбранного профиля ведёт себя как раньше.
        self.profile = profile
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

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        """Начать показ с секунды ``at`` и **дождаться картинки**, а не просто отправить LOAD.

        Без ожидания показ гаснет через секунду после команды: сторож снимает позицию
        сразу после ``play_media``, видит закономерный IDLE и считает, что играть нечего.

        ``at`` — это resume: манифест описывает весь фильм, поэтому продолжение с
        середины делается не перепаковкой «с нуля потока», а обычным LOAD с позицией.

        Зовётся один раз за показ. Перемотка сюда больше не приходит: приёмник видит весь
        фильм и мотает сам, а упаковка идёт следом за его запросами.
        """
        self._url, self._title = url, title or "torrcast"
        self._peak, self._reloads, self._stall_hits = at, 0, 0
        self._stall_at, self._stall_since = -1.0, 0.0
        self._seen, self._seek_since, self._nudged_to = -1.0, 0.0, -1.0
        self._blind, self._gone = 0, False
        budget = self.profile.revive_timeout if self._started else self.START_TIMEOUT
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
        пользователь видит её после `cast stop` и после титров, и она же оттягивает
        автовыключение ТВ. ``quit_app`` возвращает телевизор в исходное состояние
        (``app_id`` пустеет либо становится Backdrop) сразу.

        ⚠️ Закрываем **только свою** сессию (:meth:`_ours`): на том же ТВ могут жить другие
        сендеры, и кастят они через тот же Default Media Receiver. Чужой показ снимать
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
            return  # показ передают следующей серии - приложение ей и достанется
        with contextlib.suppress(Exception):
            self._cast.quit_app()
        with contextlib.suppress(Exception):
            self._cast.disconnect()
        self._cast, self._session = None, ""

    def _ours(self) -> bool:
        """Наша ли сессия сейчас на приёмнике — по трём признакам подряд.

        ⚠️ Статус берётся **кэшированный**: ``update_status`` на закрытом приёмнике
        поднимает пустой Default Media Receiver обратно (известная особенность приёмника,
        см. :meth:`_status`), а нам здесь именно закрывать. Кэш держится свежим сам:
        приёмник шлёт ``RECEIVER_STATUS`` в наш живой сокет на каждое изменение.

        * приложение не наше (``app_id`` пустой или чужой) — трогать нечего;
        * приложение то же, но сессию поднял кто-то другой — это чужой показ;
        * сессия та же, но играет не наш URL — значит, в наше приложение загрузился
          другой сендер (чужие сендеры делают ровно это, ``session_id`` при этом
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
        if pos > self._peak:  # реальный прогресс - прошлые нуджи больше не в счёт
            self._peak, self._stall_hits = pos, 0
        elif state != "IDLE" and self._peak - pos > self.REWIND:
            # Позиция уехала назад глубже допуска - это перемотка пультом: сами мы
            # прыгаем только вперёд. Максимум обязан пойти за человеком, иначе нудж
            # целится в место, которое он только что покинул. Замер на живом Q70D:
            # откат с 31:31 на 10:00, через 35 с показ выкинуло обратно на
            # 31:31 (и второй раз - с 29:55 на 30:59 нуджем через накопленные попытки).
            #
            # 🔴 ``IDLE`` из этого правила исключён: у мёртвой сессии позиции нет вовсе,
            # и ``current_time`` в ней - не «человек отмотал в начало», а «отвечать
            # некому». Замер на живом Q70D (обрыв связи, «Тачки 3»): показ споткнулся на
            # 1:12:35, приёмник ушёл в ``IDLE/ERROR`` с нулём, ноль сошёл за перемотку - и
            # повтор LOAD вернул человека не туда, где он смотрел, а к началу фильма.
            self._peak, self._stall_hits = pos, 0
        if state == "PLAYING":
            # Кадр на экране - лестница нуджей начинается с нуля, чем бы она ни кончилась.
            self._blind, self._gone = 0, False
        self._watch_seek(pos, state)
        if state == "BUFFERING":
            self._nudge(pos, front)
        else:
            self._stall_at, self._stall_since = -1.0, 0.0
        if state == "IDLE" and st.idle_reason == "ERROR" and self._reload():
            return Position(self._peak, st.duration or 0.0, True, "BUFFERING")
        if self._gone:
            # 🔴 Сторож своё отработал и передаёт эстафету воскрешению: живым такой показ
            # называть больше нельзя, хотя приёмник и рапортует BUFFERING. Состояние
            # отдаём как есть - врать о нём незачем, а решает зовущий по ``playing``.
            return Position(pos, st.duration or 0.0, False, state)
        return Position(pos, st.duration or 0.0, st.player_is_playing, state)

    def _reload(self) -> bool:
        """Повтор LOAD посреди показа: приёмник отвалился с ``IDLE/ERROR``.

        Проверенная на этом же ТВ рецептура: ровно две попытки, дальше это не наша авария.
        Грузим с ``current_time``: манифест описывает весь фильм, поэтому вернуть
        приёмник ровно туда, где он споткнулся, — это просто позиция в LOAD.
        """
        if self._reloads >= self.profile.load_retries:
            return False
        self._reloads += 1
        trace.reload(pos=self._peak, tries=self._reloads)
        print(f"приёмник отвалился на {self._peak:.0f} с - повтор LOAD", flush=True)
        try:
            self._restart_app()  # чистое приложение: залипший молчит на любой LOAD
            self._load(self._peak)
        except Exception:  # приёмник мог просто уйти - решает следующий тик
            return False
        return True

    def replay(self, at: float) -> bool:
        """Поднять СВОЙ погасший показ заново, с секунды ``at``; ``True`` - картинка вернулась.

        Терпение приёмника конечно и меньше нашего. Замер 09-08-2026 на живом Samsung
        Q70D развёл два срока, которые раньше слипались в «~4 минуты»: медиасессия
        умирает через 23.5 с стоящей картинки (:attr:`torrcast.profile.Profile.patience`),
        а приложение висит на экране ещё 301 с после её смерти
        (:attr:`torrcast.profile.Profile.app_patience`). Пока сессия жива, приёмник сам
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
        не авария показа - зовущий просто попробует ещё раз или честно погасит показ.
        """
        if not self._free():
            return False
        # Сторож начинает счёт заново: сессия новая, и её подвисы к прошлой отношения не
        # имеют. ``_peak`` - это ``at``: именно с него приёмник и поедет.
        self._peak, self._at = at, at
        self._reloads, self._stall_hits = 0, 0
        self._stall_at, self._stall_since = -1.0, 0.0
        self._seen, self._seek_since, self._nudged_to = -1.0, 0.0, -1.0
        self._blind, self._gone = 0, False
        try:
            self._restart_app()
            self._load(at)
            return self._settle(self.WAKE_TIMEOUT)
        except Exception:
            return False

    def _free(self) -> bool:
        """Свободен ли приёмник под воскрешение нашего показа.

        Свободен - это либо пустой экран (приложения нет вовсе или на нём заставка:
        ровно так выглядит ТВ, бросивший наш показ), либо всё ещё наша собственная сессия
        (:meth:`_ours`). Чужое приложение, чужая сессия в том же Default Media Receiver и
        чужой ``content_id`` в нашей - это чужой показ, и он неприкосновенен.

        Статус берётся кэшированный по той же причине, что и в :meth:`_ours`:
        ``update_status`` на закрытом приёмнике поднимает пустой Default Media Receiver
        обратно, а нам здесь именно **смотреть**, занят ли экран.
        """
        app = getattr(getattr(self._cast, "status", None), "app_id", None)
        if not app or app == self.BACKDROP_APP:
            return True
        return self._ours()

    def _nudge(self, pos: float, front: float = 0.0) -> None:
        """Расшевелить приёмник, зависший в BUFFERING на одной и той же секунде.

        Расшевеливать имеет смысл, только когда еда на столе: ``front`` — докуда упаковано,
        и пока запас впереди позиции меньше :attr:`READY_AHEAD`, приёмник ждёт **нас**, а
        не завис. Такой BUFFERING лечится упаковкой, и прыгать по нему нельзя: прыгнешь —
        уедешь в неупакованное место и заставишь раздачу паковать заново.

        Замерено на живом Q70D: на 273-й секунде показа ресивер перестал
        запрашивать сегменты и встал в BUFFERING **навсегда** — при том что следующий
        кусок лежал в tmpfs и отдавался curl'ом за миллисекунды, а живого соединения от ТВ
        в conntrack не было вовсе. То есть подвисает сам приёмник, и лечится это ``seek``:
        показ возобновляется немедленно. Такой же сторож годами держит на этом ТВ и
        другой сендер.

        ⚠️ Прыгать можно **только вперёд**, и целиться — от пройденного максимума.
        На растущем манифесте ресивер отрабатывал ``seek`` не точно, а с начала
        подходящего сегмента, и «нудж на месте» откатывал показ на ~35 с назад: позиция
        после отката меньше максимума, счётчик не сбрасывался — и получалась бесконечная
        лесенка назад (наблюдалась живьём: 2:12 → 1:58 → 1:44). С манифестом на весь
        фильм ``seek`` стал точным (замерено: позиция встаёт ровно в запрошенную), но
        правило остаётся: нудж — это лечение застрявшего куска, и лечится он тем, что
        кусок пропускают, а не тем, что его переигрывают.

        ⚠️ У лестницы есть конец (:attr:`torrcast.profile.Profile.blind_nudges`). Нудж
        лечит **застрявший кусок**, и доказательство того, что он вылечил, ровно одно -
        показанный кадр. Уехавший указатель доказательством не является: ушедший приёмник
        честно принимает ``seek`` и двигает ``current_time``, оставаясь в ``BUFFERING``, -
        замерено, 12 нуджей подряд без единого ``PLAYING``, 96 с фильма прошагано впустую.
        Поэтому после :attr:`torrcast.profile.Profile.blind_nudges` слепых прыжков сторож
        умолкает и объявляет показ погасшим (:attr:`_gone`): дальше это работа
        воскрешения (:class:`torrcast.cli._Revival`), которое поднимает сессию с последнего
        показанного кадра, а не гонит указатель дальше по фильму.
        """
        now = time.monotonic()
        if pos != self._stall_at:
            self._stall_at, self._stall_since = pos, now
            return
        if now - self._stall_since < self.profile.stall_seconds:
            return
        if front - pos < self.profile.ready_ahead:
            return  # приёмник ждёт упаковку - это наша забота, а не его зависание
        if self._blind >= self.profile.blind_nudges:
            # Прыгать больше некуда: за всю лестницу приёмник не показал ни кадра. Каждый
            # следующий прыжок стоил бы ещё 8 с неподвижной картинки и до 8 с плёнки.
            self._stall_since = now
            if not self._gone:
                self._gone = True
                print(
                    f"нуджи не дали ни кадра ({self._blind} подряд) - прыгать перестаю, "
                    "показ поднимется с последнего показанного кадра",
                    flush=True,
                )
            return
        self._blind += 1
        stuck = now - self._stall_since
        self._stall_hits += 1
        self._stall_since = now
        target = self._peak + self.profile.stall_skip * self._stall_hits
        self._nudged_to = target
        trace.nudge(pos=pos, to=target, hit=self._stall_hits, stuck=stuck, front=front)
        with contextlib.suppress(Exception):
            self._device().media_controller.seek(target)

    def _watch_seek(self, pos: float, state: str) -> None:
        """Заметить перемотку и померить, через сколько после неё появилась картинка.

        Перемотка видна только по позиции: приёмник мотает сам, никакой команды нам при
        этом не приходит. Отличаем её от хода показа по величине прыжка
        (:attr:`SEEK_JUMP`), а от собственного нуджа - по тому, куда прыгнули: сторож
        только что назвал это место сам (:attr:`_nudged_to`).

        ``IDLE`` из счёта выкинут по той же причине, что и в :meth:`position`: у мёртвой
        сессии позиции нет вовсе, и её ноль - не перемотка в начало.
        """
        seen, self._seen = self._seen, pos
        if state == "IDLE":
            self._seen = seen  # позиции не было - и сравнивать в следующий раз не с чем
            return
        now = time.monotonic()
        if self._seek_since and state == "PLAYING":
            trace.seek(frm=self._seek_from, to=self._seek_to, wait=now - self._seek_since)
            self._seek_since = 0.0
        if seen < 0.0 or abs(pos - seen) <= self.SEEK_JUMP:
            return
        if self._nudged_to >= 0.0 and abs(pos - self._nudged_to) <= self.SEEK_JUMP:
            self._nudged_to = -1.0  # прыжок наш: сторож уже записал его как нудж
            return
        self._seek_from, self._seek_to = seen, pos
        if state == "PLAYING":  # успел отработать между опросами - ждать было нечего
            trace.seek(frm=seen, to=pos, wait=0.0)
            return
        self._seek_since = now

    def seek(self, pos: float) -> None:
        """Перемотка от владеющего сендера — ровно та же MEDIA-команда, что с пульта.

        Существует ради диагностики (:data:`torrcast.cli.CTL_ENV`): автотест кнопку нажать
        не может, а вторым pychromecast её не подать вовсе — приёмник считает второе
        соединение тем же сендером (докстринг класса). Состояние сторожа (``_peak``,
        счётчики подвиса) здесь намеренно не трогается: перемотка проверяется вместе со
        сторожем, и подчищать за собой его вход значило бы проверять не то.
        """
        self._device().media_controller.seek(pos)

    def pause(self) -> None:
        self._device().media_controller.pause()

    def resume(self) -> None:
        self._device().media_controller.play()

    def _load(self, at: float = 0.0) -> None:
        controller = self._device().media_controller
        # BUFFERED, а не LIVE: манифест VOD знает длительность целиком, и ресивер
        # рисует шкалу с общим временем - перемотка пультом работает.
        controller.play_media(
            self._url,
            HLS_TYPE,
            title=self._title,
            stream_type="BUFFERED",
            media_info=HLS_HINTS,
            current_time=at,
        )
        controller.block_until_active(timeout=30)
        # Чья сессия на приёмнике - запоминаем здесь: по ней :meth:`_ours` отличит наш
        # показ от чужого, когда придёт пора закрывать приложение.
        self._session = getattr(self._cast.status, "session_id", "") or ""

    def _settle(self, budget: float) -> bool:
        """Дождаться, пока приёмник действительно заиграет; отказ LOAD - повторить LOAD.

        ``IDLE`` без причины - это «ещё грузится», его терпим до конца ``budget``: ресивер
        сперва тянет манифест и первый сегмент. А вот причина говорит, что LOAD не взяли,
        и ждать бессмысленно:

        * ``ERROR`` - ресивер не смог начать;
        * ``IDLE`` дольше :data:`STUCK_SECONDS` - LOAD не взяли молча. Такое ловилось
          после перепаковки: приёмник стоял в IDLE при живых сегментах.

        Повтор LOAD - один счётчик на весь показ (:attr:`_reloads`), и потолок ему ставит
        профиль приёмника (:attr:`torrcast.profile.Profile.load_retries`), а не бюджет
        ожидания: лестница ожидания не имеет права плодить свои попытки. Иначе счёт вёлся
        бы временем, и на неигравшем релизе в приёмник уходил бы десяток LOAD подряд, всё
        глубже загоняя его, пока прогон висит перед пустым экраном. Исчерпав повторы, честно
        возвращаем ``False`` - зовущий назовёт причину строкой, а не оставит человека в
        бесконечной петле LOAD. Каждый повтор ложится в след (:func:`torrcast.trace.reload`).

        ⚠️ ``INTERRUPTED`` поводом для повтора НЕ является: так ресивер отчитывается о
        КОНЦЕ ПРЕЖНЕЙ сессии, которую оборвал наш же новый LOAD. Повтор на него сбивает
        только что принятый LOAD - проверено живьём, показ на этом и умер.

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
                if self._reloads >= self.profile.load_retries:
                    return False  # повторы LOAD исчерпаны - показ не начался, гаснем честно
                self._reloads += 1
                trace.reload(pos=self._peak, tries=self._reloads)
                tried = time.monotonic()
                print(
                    f"LOAD не взяли ({self._why()}) - повтор {self._reloads} "
                    f"из {self.profile.load_retries}",
                    flush=True,
                )
                self._restart_app()
                self._load(self._at)
        return False

    def _restart_app(self) -> None:
        """Закрыть приложение приёмника **и своё соединение** — следующий LOAD уходит в
        чистое с обеих сторон.

        ⚠️ Одного `quit_app` мало, замерено трижды подряд: приложение честно
        закрывается (``app_id`` становится ``None``), следующий LOAD по ТОМУ ЖЕ сокету
        поднимает его обратно — и показ не начинается, приёмник стоит в IDLE до самой
        смерти юнита. При этом новый процесс с новым соединением на том же ТВ поднимает
        картинку за 3 с. Значит, чинить надо не только приёмник, но и свою сессию.
        """
        print("приёмник залип - закрываю приложение и соединение, гружу заново", flush=True)
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
        # Receiver - «вышел в Home, а каст открылся снова». Поэтому
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

            hush_cosmetic_noise()  # косметика 8443 на каждом подключении - не наша беда
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

    🔴 Чего mock НЕ моделирует и промоделировать не может: вторую голову чтения - прогрев
    фильма на диск (:mod:`torrcast.warm`). Прогрев работает впрок в фоне на протяжении
    ВСЕГО показа и трогается с места лишь при играющей картинке, на остатке процессора
    (:meth:`torrcast.warm.Warmer._wait_for_picture`), а mock проигрывает фильм за секунды
    стенных часов, а не в реальном темпе. Окна, в котором его ffmpeg успел бы уложить хоть
    кусок на диск, у сухого прогона попросту нет, и вторая голова под заглушкой не
    появляется ни разу - замерено: :meth:`torrcast.warm.Warmer._run` за сухой прогон не
    зовётся вовсе. Поэтому зелёный сухой прогон приёмкой ПРОГРЕВА не является: сам прогрев
    сверяется отдельно, гоняя :class:`torrcast.warm.Warmer` напрямую (tests/test_warm.py),
    и на живом ТВ с выключенным интернетом.

    ⚠️ Сделать заглушку реально-темповой, чтобы прогрев в ней ожил «как на живом», нельзя:
    сухой прогон стал бы длиться как сам фильм и потерял бы детерминизм, ради которого он
    и существует, а прогрев всё равно не успел бы уложить фильм за один прогон показа. Это
    осознанная граница модели, а не недоделка: заглушка не изображает того, чего проверить
    на ней честно нельзя, - и молчаливо не делает вид, что прогрев на mock работает.
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

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        self._url = url
        self._seen, self._still, self._loads, self._dead = -1.0, 0.0, 0, False
        self._open(url, at)

    def _open(self, url: str, at: float = 0.0) -> None:
        """Открыть поток с секунды ``at``: проверка ответа, декодер, счётчики приёмки.

        Зовётся и на первый LOAD, и на каждый повтор — свой (:meth:`_wait`) и чужой
        (:meth:`replay`). Порядок обязателен: сперва спрашиваем источник и только потом
        рушим прошлый декодер, иначе неудачный повтор гасил бы ещё живую картинку.
        """
        self._probe(url)  # первый ответ проверяем сами: TLS, доступность, CORS
        self._quiet()
        self._done = threading.Event()  # прошлые потоки остановлены, у этого показа свой
        self._last = -1  # нумерация сегментов пойдёт с места подъёма, а не подряд с прошлой
        self._err = tempfile.TemporaryFile()  # noqa: SIM115 - живёт всё воспроизведение
        self._start = at
        # ⚠️ Опции TLS ставятся только под https-адрес: на http ffmpeg не «игнорирует
        # лишнее», а падает с «Option tls_verify not found» ещё до открытия входа -
        # то есть на дефолтном транспорте mock не декодировал бы ничего.
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
            self._close_log()
            raise InfraError("ffmpeg не установлен") from exc
        self._pos = Position(0.0, 0.0, True)
        self._follower = None
        for target in (self._follow, self._audit):
            thread = threading.Thread(target=target, args=(url,), daemon=True)
            thread.start()
            if target is self._follow:
                self._follower = thread

    def _close_log(self) -> None:
        """Закрыть журнал ffmpeg. Зовётся с двух сторон, поэтому забирает файл себе."""
        err, self._err = self._err, None
        if err is not None:
            err.close()

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
        pos, moving = self._pos.pos, self._pos.pos > self._seen
        self._seen = pos
        if self._pos.playing and moving:
            self._still, self._loads = 0.0, 0
            return Position(pos, dur, True, "PLAYING")
        if self._over():
            return Position(pos, dur, False, "")  # декодер дошёл до конца входа - это титры
        if self._wait(pos):
            # Приёмник ждёт картинку и показ считает живым - как ТВ в BUFFERING.
            return Position(pos, dur, True, "BUFFERING")
        return Position(0.0, dur, False, "IDLE")

    def _over(self) -> bool:
        """Кончился ли вход честно: декодер вышел нулём, значит фильм доигран, а не оборван."""
        return self._proc is not None and self._proc.poll() == 0

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

    def replay(self, at: float) -> bool:
        """Поднять СВОЙ погасший показ с секунды ``at``; ``True`` - картинка вернулась.

        Тот же договор, что и у :meth:`ChromecastReceiver.replay`: позиция приходит
        снаружи (у мёртвой сессии её нет), исключения наружу не выпускаются, а ``True``
        говорится только про действительно вернувшуюся картинку, а не про отправленный
        LOAD. Ждать её дольше :attr:`WAKE_TIMEOUT` незачем: попытка тут не одна.

        ⚠️ Чужой показ заглушка не видит и видеть не может - :meth:`ChromecastReceiver._free`
        здесь не воспроизводится ничем. Что приёмник занят чужим, проверяется только на
        живом ТВ.
        """
        if not self._url or self.clock.monotonic() < self._sulk:
            return False  # приёмник поймал 404 и ближайшие минуты не берёт LOAD вовсе
        try:
            self._open(self._url, at)
        except (InfraError, OSError):
            return False  # источника всё ещё нет - зовущий попробует ещё раз или погасит
        self._seen, self._still, self._loads = at, 0.0, 0
        deadline = self.clock.monotonic() + self.WAKE_TIMEOUT
        while self.clock.monotonic() < deadline:
            self.clock.sleep(1.0)
            if self._pos.pos > at:  # декодер поехал - картинка на экране
                self._dead = False
                return True
            if not self._pos.playing:
                break  # декодер лёг, не начав: показа нет, и врать о нём нельзя
        self._quiet()
        return False

    def _session(self) -> Any:
        import requests

        session = requests.Session()
        session.verify = self.ca or True
        return session

    def _probe(self, url: str) -> None:
        import requests

        try:
            response = self._session().get(url, timeout=30)
            self._caught(response)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise InfraError(f"приёмник не забрал манифест: {why(exc)}") from exc
        if response.headers.get(_CORS_HEADER) != "*":
            raise InfraError(f"в ответе нет {_CORS_HEADER}: * - Chromecast такое молча не играет")

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


def trust_anchor(cert: str) -> str:
    """Чему приёмник должен доверять, проверяя нашу раздачу.

    Серт выпущен настоящим CA (LE) — доверяем **системному хранилищу**: ровно
    так его проверит ТВ, и только такая проверка закрывает требование Chromecast к
    доверенному HTTPS. Серт self-signed (дефолт `install.sh` до доставки LE) — доверяем
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
        return cert  # нечитаемый серт - пусть падает там, где это видно
    if len(anchors) == 1 and anchors[0].get("subject") == anchors[0].get("issuer"):
        return cert
    return ""


def make_receiver(
    kind: ReceiverKind, address: str = "", ca: str = "", profile: Profile = CAUTIOUS
) -> Receiver:
    if kind == "mock":
        return MockReceiver(trust_anchor(ca) if ca else "", profile=profile)
    return ChromecastReceiver(address, profile=profile)
