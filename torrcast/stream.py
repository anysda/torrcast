"""TorrServer, ffprobe и упаковка потока в HLS. Своего CDN-кода нет: раздачу отдаёт
TorrServer (кэш в RAM, на диск не пишем), пакует ffmpeg (§3 ТЗ). Формат для ТВ
зафиксирован: HLS, сегменты MPEG-TS ~4 с, один вариант в манифесте, видео ``copy``,
аудио **всегда** в AAC stereo 192k, CORS ``*`` на всех ответах.
"""

from __future__ import annotations

import bisect
import contextlib
import hashlib
import http.server
import json
import math
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Final, NamedTuple
from urllib.parse import quote

from torrcast import InfraError, why
from torrcast.parse import VIDEO_EXT
from torrcast.timing import TIMELINE_ENV, mark

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    import requests

    from torrcast.state import Config

__all__ = [
    "HLS_SEGMENT_SECONDS",
    "KEYS_WAIT",
    "MAX_SEGMENT_BYTES",
    "MIXED_PREFIX",
    "PILOT_TIMEOUT",
    "RUNTIME_GUESS",
    "AudioTrack",
    "Feed",
    "FilmKeys",
    "Grid",
    "HlsServer",
    "Media",
    "Packer",
    "TorrFile",
    "TorrServer",
    "Warmup",
    "bitrate_mbit",
    "ffmpeg_pack_command",
    "film_keys",
    "forget_playing",
    "grid_for",
    "hls_base",
    "hls_dir",
    "mark_playing",
    "merge_tracks",
    "our_address",
    "pack_start",
    "parse_manifest",
    "pick_video_file",
    "playing_flag",
    "probe",
    "segment_name",
    "segment_slot",
    "start_play_unit",
    "stop_play_unit",
    "unit_active",
    "unit_key",
    "unit_why",
    "voice_order",
    "warm_at",
    "warm_file",
]

#: Шаг сетки сегментов, секунды. Было 4 — стало 10, и это не вкусовщина, а
#: измерение (§6 SPEC-v2, живой Q70D 05-08-2026, «Моана» 2016, место 1:24).
#:
#: Спотыкач на 1:24 оказался **нашей нарезкой, а не фильмом и не роем**. Доказано так:
#:
#: * тот же битстрим видео (``-c:v copy``) и тот же AAC, но одним прогрессивным mp4 —
#:   ТВ проходит место 1:24 без единого BUFFERING (70 с показа, 0 подвисов);
#: * сеткой по 4 с — встаёт намертво на границе сегмента и сам не оживает никогда
#:   (5 прогонов из 5: четыре production-овских и один в диагностическом стенде);
#: * сдвиг сетки на 0.21 с (упаковка с ``-ss 20``) — встаёт там же;
#: * SPS/PPS в каждый кадр (``dump_extra``) — встаёт там же;
#: * рез строго по ключевым кадрам — встаёт там же;
#: * сеткой по 10 с — проходит чисто (0:00→1:42, ни одного BUFFERING).
#:
#: ⚠️ Объяснение «граница не должна трогать тяжёлый GOP» **проверено и не подтвердилось**
#: (замеры на живом Q70D 05-08-2026, «Моана 2» 2024, карта опорных кадров снята
#: ``scripts/keyframes.py``). Сетка 10 с на этом файле:
#:
#: * режет 585 GOP из 1118, в том числе самый тяжёлый в фильме (13.31 МБ / 10.38 с,
#:   место 87:11, граница ровно внутри него) — показ идёт чисто, ни одного BUFFERING;
#: * оставляет 12 сегментов, внутри которых нет ни одного опорного кадра (GOP длиннее
#:   сетки), первый из них — 1:10…1:20 — тоже играется чисто.
#:
#: То есть ни «тяжёлый GOP разрезан», ни «в сегменте нет опорного кадра» сами по себе
#: приёмник не роняют, и правила «сетка обязана быть длиннее самого длинного GOP» из
#: этих цифр не следует.
#:
#: Что подтвердилось: провал зависит от **фазы** сетки, а не от веса GOP. Сетка 4 с на
#: «Моане» 2016 воспроизводимо встаёт ровно на 84.0 с, когда упаковка начата с нуля
#: (BUFFERING, позиция стоит, сторож вытаскивает нуджем через ~9 с), и та же сетка 4 с
#: в том же месте проходит чисто, когда упаковка начата с 1:10 — то есть когда границы
#: сегментов сдвинуты относительно фильма. Единственный внятный вывод, который цифры
#: держат: 10 с — это в 2.5 раза меньше границ, чем 4 с, и на всех замеренных местах
#: обоих фильмов эта сетка проходит. Класс НЕ закрыт: правило, по которому можно было бы
#: заранее сказать, какая именно граница убьёт показ, не найдено (см. отчёт по §6).
#:
#: ⚠️ Это был шаг сетки, а не её место в фильме: **фаза** сетки до 06-08-2026 зависела от
#: того, откуда начата упаковка. ``split_by_time`` отсчитывает границы от ПЕРВОГО пакета
#: прогона, а ``-ss`` уводит ffmpeg на опорный кадр не позже запрошенного места, поэтому
#: после рестарта с 70 с сегмент с именем ``v17`` (сетка 4 с, то есть «68.0 с») начинался
#: на 67.55 с. Теперь границы абсолютные: см. :class:`Grid` и :func:`pack_start`.
HLS_SEGMENT_SECONDS: Final = 10
#: Каталог одного прогона упаковки внутри каталога показа. ffmpeg пишет сегменты сюда, а
#: наружу они попадают переименованием (:meth:`Packer.publish`) — по двум причинам:
#:
#: * готовность. Сегментный муксер, в отличие от hls, не пишет через временный файл:
#:   файл появляется пустым и наполняется. «Есть файл» перестало значить «кусок готов»,
#:   а вот «появился следующий» — значит, и это видно только внутри прогона;
#: * докатка. Прогон почти всегда начинается раньше своей границы (``-ss`` уводит на
#:   опорный кадр), и этот огрызок ffmpeg кладёт под именем предыдущего сегмента. Отдать
#:   его наружу нельзя: под этим именем уже может лежать честный сегмент прошлого прогона.
PACK_DIR: Final = "pack"

#: Каталог перекодированных кусков (§6.2, :mod:`torrcast.recode`). Лежит рядом с
#: :data:`PACK_DIR` внутри каталога показа, поэтому уборка сегментов (`v*.ts` верхнего
#: уровня) его не задевает, а :meth:`Feed.stop` сносит целиком.
RECODE_DIR: Final = "recode"
#: Имя склеенного куска (:func:`merge_tracks`) внутри каталога прогона. Начинается **не**
#: с ``v``: каталог прогона перебирается глобом ``v*.ts``, и склейка не должна попасть в
#: него ни как готовый сегмент, ни как признак «следующий открыт, прошлый дописан».
MIXED_PREFIX: Final = "mix"
#: Список сегментов, который ведёт сам ffmpeg: ``имя,начало,конец`` на каждый закрытый
#: кусок. Приёмнику он не отдаётся — по нему показ сверяет, что нарезал ровно то, что
#: обещал в манифесте (:meth:`Packer.drift`).
PACK_LIST: Final = "pack.csv"
#: Сколько байт тянем под меню одним местом (:func:`warm_at`): первый сегмент — это
#: 10–20 с видео со звуком, то есть десятки мегабайт.
HEAD_WARM: Final = 32 << 20
#: Сколько головы хватает, чтобы ffmpeg открыл вход, когда играть будем из середины:
#: заголовок контейнера и индекс, но не картинка. Тянуть все 32 МБ начала при продолжении
#: с середины вредно: это чужие байты, и они отбирают полосу у нужного места.
#:
#: Число одно на все контейнеры быть не может, и в этом была ошибка первой версии (§7.3
#: SPEC-v2, «голова съедает весь бюджет»): 8 МБ выбраны с запасом под ``moov`` mp4, а
#: у mkv в голове лежат только EBML-заголовок, SeekHead, Info и Tracks — килобайты. На
#: холодном рое эта разница и есть весь бюджет раздумья: пока качается лишнее начало,
#: до места позиции дело не доходит.
#: У mp4 запас остаётся: ``moov`` бывает и на мегабайты (у «Моаны 2» от YTS — 5.3 МБ), а
#: без него ffmpeg вход не откроет вовсе.
HEAD_OPEN: Final = {"mkv": 1 << 20, "mp4": 8 << 20}
#: Контейнер неизвестен (карта из кэша прошлой версии, чужой файл) — берём больший кусок:
#: лишние мегабайты дешевле, чем ffmpeg, который не смог открыть вход.
HEAD_OPEN_DEFAULT: Final = 8 << 20
#: Потолок ожидания прогрева: дальше это уже не прогрев, а висящий поток.
WARM_TIMEOUT: Final = 120.0
#: Потолок пробного прогона в один кадр (:func:`pack_start`). Обычная цена — 0.5–1.7 с,
#: но на холодном рое это чтение нового места, и оно упирается в раздачу. Число
#: вынесено сюда не ради красоты: из него и из соседних потолков складывается бюджет
#: старта юнита, который ждёт CLI (``torrcast.cli.START_BUDGET``, §7.4 SPEC-v2).
PILOT_TIMEOUT: Final = 60.0
#: Сколько ждём чужого снятия карты опорных кадров, прежде чем снимать самим.
KEYS_WAIT: Final = 40.0
#: Замок снятия карты считается живым столько секунд: дальше это брошенный хвост.
KEYS_LOCK: Final = 60.0
#: Допуск при сравнении времени границы с меткой кадра: границы сетки стоят на опорных
#: кадрах, но метки одного и того же кадра при упаковке от нуля и из середины файла
#: отличаются на кадр (ffmpeg не пускает dts ниже нуля). Полкадра 24 к/с — 0.02 с.
SPLIT_SLACK: Final = 0.02
#: На сколько мультиплексор mpegts сдвигает метки времени, если его не остановить:
#: ``muxdelay`` (0.7 с) + ``muxpreload`` (0.7 с) секунд ко ВСЕМ pts/dts выходного потока.
#:
#: Число здесь не ради вычислений — ни одна строка на него не умножает. Оно названо,
#: потому что дважды стоило расследования: :func:`pack_start` глушил его с самого начала,
#: а :func:`ffmpeg_pack_command` — нет, и сегменты уезжали на ТВ со временем фильма плюс
#: 1.4 с. Замерено на стенде 07-08-2026 («Тачки 3», граница 3965.670): по умолчанию первый
#: кадр сегмента 3967.070, с ``-muxdelay 0 -muxpreload 0`` — 3965.670, точно в карту.
MPEGTS_MUX_DELAY: Final = 1.4
_SEGMENT_RE: Final = re.compile(r"v(\d+)\.ts")
#: Флажок «на экране картинка»: его кладёт показ, когда приёмник впервые ответил
#: ``PLAYING``, и ждёт CLI. Спросить приёмник из CLI нельзя — сендер к нему ровно один
#: (:mod:`torrcast.cast`), поэтому доказательство картинки передаётся файлом (§4 SPEC-v2).
PLAYING_FLAG: Final = "playing.flag"
#: Аудио всегда перекодируется: passthrough AC3/DTS запрещён (§3).
AUDIO_CODEC: Final = "aac"
AUDIO_BITRATE: Final = "192k"
AUDIO_CHANNELS: Final = 2
#: Сколько Мбит/с занимает наша звуковая дорожка в том, что уезжает на ТВ.
#:
#: ⚠️ Дорожка ИСХОДНИКА тут ни при чём, сколько бы она ни весила: показ всегда
#: перекодирует звук в AAC (см. :func:`ffmpeg_pack_command`), поэтому в сегмент уезжает
#: ровно :data:`AUDIO_BITRATE`, а не 1.5 Мбит/с DTS «Тачек 3». Считать «видео + выбранная
#: дорожка» было бы враньём в полтора мегабита.
AUDIO_MBIT: Final = 0.192
#: Во сколько раз mpegts тяжелее того, что в него упаковано: заголовки 4 байта на 188,
#: PAT/PMT/PCR и набивка на границах PES. Замер 06-08-2026 на восьми сегментах-копиях
#: «Моаны 2» подряд: поправка «контейнер → ТВ» сходилась к 4.10…4.26 Мбит/с при
#: контейнере 19.16 и видеодорожке 14.33 — то есть уезжало (14.33 + 0.19) × 1.03.
TS_OVERHEAD: Final = 1.03
#: Потолок веса ОДНОГО сегмента: сколько байт разрешено уехать на ТВ одним куском.
#:
#: 🔴 Это и есть механизм §6-подвиса, найденный замером 07-08-2026 (§6.2.4 SPEC-v2).
#: Приёмник Q70D срывается в BUFFERING на 4–8 с ровно на границе, за которой лежит
#: сегмент тяжелее ~19 МБ, и снимается сам, **повторно скачав** уже полученные куски —
#: то есть выбрасывает буфер и набирает его заново. Секунды тут ни при чём, и это
#: доказано в обе стороны на живом ТВ:
#:
#: * 20.0 с и 14.3 МБ («Моана 2», два лёгких куска слиты в один) — прошло чисто;
#: * 19.9 с и 24.2 МБ (та же «Моана 2», тяжёлый кусок) — приёмник не подвис, а **потерял
#:   сессию** целиком;
#: * 16.934 с / 18.7 МБ — чисто, 16.892 с / 20.3 МБ («Тачки 3») — стоп 8 с: одна и та же
#:   длина, разный вес, разный исход;
#: * тот же тяжёлый кусок, разрезанный пополам (12.0 и 9.0 МБ), — чисто.
#:
#: Граница отбраковки лежит между 18.7 МБ (чисто) и 19.4 МБ (стоп), поэтому потолок
#: поставлен на 16 МБ — запас 15 % и ни одного лишнего сегмента в манифесте на лёгком
#: кино (там 10 с весят 6–8 МБ и правило не срабатывает вовсе).
MAX_SEGMENT_BYTES: Final = 16_000_000
#: Типовая длительность до ffprobe (фильм 2 ч, серия 45 мин): только для прикидки битрейта.
RUNTIME_GUESS: Final = {"movie": 7200.0, "tv": 2700.0, "other": 7200.0}

_TIMEOUT: Final = 30.0
_UNIT_NAME: Final = "torrcast-play"
#: Описание юнита несёт ключ показа — по нему ``status`` знает, что играет (§2.5).
_UNIT_TAG: Final = "torrcast: "
#: Что пробрасывается в юнит: без этого показ уедет на прод-пути вместо dev-овских.
_PASS_ENV: Final = (
    "TORRCAST_CONFIG",
    "TORRCAST_STATE",
    "TORRCAST_TRACE",
    "TORRCAST_CTL",
    TIMELINE_ENV,
)


def bitrate_mbit(size: int, duration: float) -> float:
    """Средний битрейт раздачи, Мбит/с — предел декодера Q70D ~20 (§3)."""
    return size * 8 / duration / 1e6 if size > 0 and duration > 0 else 0.0


@dataclass(frozen=True, slots=True)
class TorrFile:
    index: int
    name: str
    size: int = 0

    @property
    def base(self) -> str:
        """Имя без пути: сезон живёт в каталоге, номер серии — в имени файла (§2.4)."""
        return self.name.replace("\\", "/").rsplit("/", 1)[-1]


#: Языковые коды, которые ffprobe отдаёт для русской дорожки.
_RU_LANG: Final = frozenset({"rus", "ru", "russian", "рус"})
#: Коды, которые языка не называют: дорожка без тега или тег-заглушка. Тогда язык
#: приходится читать из заголовка — у половины живых раздач он там и написан.
_VAGUE_LANG: Final = frozenset({"", "und", "unk", "unknown", "mul", "mis", "zxx", "qaa"})
#: Заголовок называет НЕ русскую озвучку. Нужен ровно потому, что «Дубляж» пишут
#: кириллицей и для казахской, и для украинской дорожки («Тачки 3»: rus/ukr/kaz — у
#: всех трёх заголовок «Дубляж», и различает их только тег языка).
_FOREIGN_TITLE_RE: Final = re.compile(
    r"укр|ukr|каз|kaz|қаз|беларус|bel\b|eng\b|англ|original|ориг", re.IGNORECASE
)
#: Заголовок называет русскую озвучку: либо прямо, либо маркером перевода.
_RU_TITLE_RE: Final = re.compile(
    r"\brus?\b|русск|дубляж|дублир|многоголос|закадр|двухголос|одноголос|перевод|авторск",
    re.IGNORECASE,
)
#: Служебные дорожки: тифлокомментарий и комментарии съёмочной группы. Русские,
#: осмысленные и совершенно не то, что человек хочет услышать. Живой случай —
#: «Тачки 3»: дорожка №2 «Дубляж для слабовидящих» стоит сразу за нормальным дубляжом.
_SERVICE_RE: Final = re.compile(
    r"слабовидящ|тифлокоммент|коммент|commentary|audio\s*descr|described",
    re.IGNORECASE,
)
#: Оригинальная дорожка — последняя ступень лестницы, но выше чужого дубляжа.
_ORIGINAL_RE: Final = re.compile(r"original|\borig\b|ориг", re.IGNORECASE)
#: Вид перевода по заголовку → ступень. Порядок здравого смысла (правка владельца
#: 06-08 к §2 SPEC-v2): дубляж → многоголосый/закадровый → прочий русский → оригинал.
#: Регексы писаны по живой выдаче: «Дубляж. (MovieDalen)», «MVO (LostFilm)»,
#: «[TVShows][MVO]», «DUB-Blu-ray CEE», «MVO-студия «Омикрон»», «AVO-Сербин», «VO-Есарев».
_VOICE_STEPS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("дубляж", re.compile(r"дубляж|дублир|\bdub\b|\bдб\b", re.IGNORECASE)),
    ("многоголосый", re.compile(r"многоголос|закадр|\bmvo\b|\bпм\b|\bлм\b", re.IGNORECASE)),
    ("двухголосый", re.compile(r"двухголос|\bdvo\b|\bдвг\b", re.IGNORECASE)),
    ("одноголосый", re.compile(r"одноголос|авторск|\bavo\b|\bvo\b|\bло\b|\bап\b", re.IGNORECASE)),
)
#: Ступени, на которые встаёт нерусская дорожка и служебная.
STEP_RU_PLAIN: Final = len(_VOICE_STEPS)  #: русская без маркера перевода
STEP_ORIGINAL: Final = STEP_RU_PLAIN + 1  #: оригинал
STEP_FOREIGN: Final = STEP_RU_PLAIN + 2  #: чужой дубляж: украинский, казахский
STEP_SERVICE: Final = STEP_RU_PLAIN + 3  #: тифлокомментарий и комментарии
#: Технический хвост заголовка: «DUB (Rus) / AC3 / 6 ch / 384 kbps / 48 kHz». Человеку
#: в строке запуска он не нужен, а подписью озвучки (она же ключ памяти) быть мешает.
_TECH_RE: Final = re.compile(
    r"^(?:ac3|eac3|dts(?:-hd)?(?:\s*ma)?|aac|mp3|flac|opus|truehd|pcm|lpcm|dd\+?|ddp"
    r"|\d+\s*ch|\d+\s*kbps|\d+(?:[.,]\d+)?\s*k?hz|\d+\s*bit|\d\.\d)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AudioTrack:
    index: int
    language: str | None = None
    title: str | None = None
    codec: str | None = None
    channels: int = 0

    @property
    def label(self) -> str:
        """Человеческая подпись озвучки: «rus · Дубляж (MovieDalen)».

        Она же ключ памяти (:attr:`torrcast.state.Entry.voice`), поэтому технический
        хвост из неё убран: «DUB (Rus) / AC3 / 6 ch / 384 kbps / 48 kHz» — это одна и та
        же озвучка что с битрейтом в имени, что без.
        """
        parts = [p for p in (self.language, self.clean_title) if p]
        return " · ".join(parts) if parts else f"дорожка {self.index + 1}"

    @property
    def clean_title(self) -> str:
        """Заголовок без технического хвоста (кодек, каналы, битрейт, частота)."""
        kept: list[str] = []
        for chunk in (self.title or "").split("/"):
            if _TECH_RE.match(chunk.strip()):
                break
            kept.append(chunk.strip())
        return " / ".join(p for p in kept if p).strip(" .")

    @property
    def is_russian(self) -> bool:
        """Русская ли дорожка. Тег языка сильнее заголовка: «Дубляж» с тегом ``kaz`` —
        казахский дубляж, и слышать его никто не хотел (живой случай «Тачки 3»).
        """
        lang = (self.language or "").strip().casefold()
        if lang in _RU_LANG:
            return True
        if lang not in _VAGUE_LANG:  # язык назван, и он не русский — заголовок не спорит
            return False
        title = self.title or ""
        return bool(_RU_TITLE_RE.search(title)) and not _FOREIGN_TITLE_RE.search(title)

    @property
    def kind(self) -> str:
        """Вид перевода словами: ``дубляж``, ``многоголосый``…; пусто — маркера нет."""
        title = self.title or ""
        return next((name for name, rx in _VOICE_STEPS if rx.search(title)), "")

    @property
    def step(self) -> int:
        """Ступень лестницы «самой нормальной» озвучки; меньше — ближе к дефолту."""
        title = self.title or ""
        if _SERVICE_RE.search(title):
            return STEP_SERVICE
        if not self.is_russian:
            return STEP_ORIGINAL if _ORIGINAL_RE.search(title) else STEP_FOREIGN
        steps = (i for i, (name, _) in enumerate(_VOICE_STEPS) if name == self.kind)
        return next(steps, STEP_RU_PLAIN)


def voice_order(track: AudioTrack) -> tuple[int, int]:
    """Место дорожки в очереди на дефолт: ступень, а при равной ступени — порядок в файле.

    Порядок внутри ступени берём авторский: сборщик раздачи кладёт первой ту озвучку,
    которую сам считает основной («Моана 2»: три дубляжа подряд, первым MovieDalen).
    """
    return (track.step, track.index)


@dataclass(slots=True)
class Warmup:
    """Фоновое добавление magnet в TorrServer под меню (§3.1)."""

    magnet: str
    torrent_hash: str = ""
    error: InfraError | None = None
    thread: threading.Thread | None = None

    def result(self, timeout: float = 30.0) -> str:
        """Дождаться hash прогретой раздачи."""
        if self.thread is not None:
            self.thread.join(timeout)
        if self.error is not None:
            raise self.error
        if not self.torrent_hash:
            raise InfraError("TorrServer не принял раздачу за отведённое время")
        return self.torrent_hash


@dataclass(frozen=True, slots=True)
class Media:
    """Что ffprobe вычитал из потока: длительность, звуковые дорожки и кодек видео."""

    duration: float = 0.0
    tracks: tuple[AudioTrack, ...] = ()
    #: Настоящий кодек видео. Имя раздачи врёт или молчит (у «Моаны 2» кодек назван
    #: в 2 именах из 8), а видео мы отдаём ``copy`` — значит ресивер получит ровно его.
    video: str | None = None
    #: Высота кадра из потока. Имя раздачи о качестве тоже молчит через раз, а сказать
    #: человеку «1080p» вместо «?» мы обязаны из того же ffprobe, что уже прочитан.
    height: int = 0
    #: Ширина кадра. Нужна не ради красоты: у широкоформатного фильма чёрные поля
    #: обрезаны, и 1920×800 — это честный 1080p, а не «800p» (:attr:`frame`).
    width: int = 0
    #: Битрейт ВИДЕОДОРОЖКИ, бит/с; ``0`` — паспорт его не несёт (:func:`_video_bps`).
    #:
    #: Это единственное честное «сколько уедет на ТВ»: контейнер тяжелее видео на все
    #: свои дорожки и субтитры, и разрыв не константа — у «Моаны 2» (10 озвучек, 12
    #: субтитров) 4.8 Мбит/с, у «Тачек 3» 2.9, у «Моаны» 2016 — 0.6. Пока этого числа не
    #: было, разрыв набирался вслепую по первым выложенным сегментам
    #: (:meth:`torrcast.recode.Weights.calibrate`) — 8–10 сегментов показа мимо профиля.
    video_bps: float = 0.0

    @property
    def delivered_mbit(self) -> float:
        """Сколько Мбит/с уедет на ТВ в среднем по фильму; ``0`` — паспорт не сказал.

        Видеодорожка идёт копией, звук — всегда AAC (:data:`AUDIO_MBIT`), сверху
        оверхед mpegts (:data:`TS_OVERHEAD`). Отсюда же считается и профиль тяжести
        каждого куска: тот же множитель, только байты берутся из карты опорных кадров.
        """
        if self.video_bps <= 0:
            return 0.0
        return (self.video_bps / 1e6 + AUDIO_MBIT) * TS_OVERHEAD

    def weight_mbit(self, size: int) -> float:
        """Вес релиза для потолка отбраковки, Мбит/с: паспорт, а не размер файла.

        Отбраковка (``bitrate_hard_mbit``, §7.6 SPEC-v2) спрашивает «сколько придётся
        перекодировать непрерывно», а это вес **видеодорожки**: звук показ всё равно
        сжимает в AAC 192k, субтитры и лишние озвучки не уезжают никуда. Размер файла на
        длительность отвечает на другой вопрос — «сколько весит контейнер», — и отвечает
        тем хуже, чем больше в релизе дорожек: у «Моаны 2» контейнер 19.2 против видео
        14.3, у «Тачек 3» — 17.0 против 14.1 (замер 07-08-2026). То есть потолок 25 мерил
        десять озвучек заодно с картинкой и мог забраковать релиз, который тянется.

        Паспорт молчит (mp4 без тегов, кривой ремукс) — считаем по размеру, как раньше:
        завышенная оценка лучше пропущенного 4K-ремукса на 50 Мбит/с.
        """
        return self.video_bps / 1e6 if self.video_bps > 0 else bitrate_mbit(size, self.duration)

    @property
    def frame(self) -> int:
        """Ступень лестницы качества, к которой относится кадр.

        По одной высоте судить нельзя: 1920×800 (обрезанный скоуп) и 1150×574 дают 800 и
        574 — числа соседние, а это 1080p и SD. Ширина отвечает на это однозначно, потому
        что кадрируют по вертикали: считаем, во что кадр развернулся бы в 16:9, и берём
        большее из двух.
        """
        return max(self.height, self.width * 9 // 16)

    @property
    def quality(self) -> str:
        """Качество словами: ``1080p``; ноль высоты — честный ``?``.

        Ступени лестницы называются как принято (2160p/1080p/720p), всё, что ниже, —
        своей высотой: «574p» у «Моаны 2» и есть ответ на вопрос «что уехало на ТВ».
        """
        for step in (2160, 1080, 720):
            if self.frame >= step * 0.95:
                return f"{step}p"
        return f"{self.height}p" if self.height else "?"

    @property
    def video_warning(self) -> str:
        """Пустая строка, если ресиверу это точно по зубам (§9: HEVC и экзотика)."""
        if self.video in (None, "h264"):
            return ""
        return f"внимание: видео {self.video} — ресивер может не взять, а мы не перекодируем"

    def default_track(self) -> int:
        """«Самая нормальная» озвучка — та, что играет без вопросов (правка владельца
        06-08 к §2 SPEC-v2): русский дубляж → русский многоголосый → прочий русский →
        оригинал → чужой дубляж; служебные дорожки (тифлокомментарий, комментарии) — в
        самый низ. Выбор не молчаливый: подпись дорожки печатается в строке запуска.
        """
        if not self.tracks:
            return 0
        return min(self.tracks, key=voice_order).index

    def find_voice(self, label: str) -> int | None:
        """Дорожка с такой подписью (память озвучки, §2 SPEC-v2); ``None`` — такой нет.

        Сравниваем подписи, а не номера: релиз мог смениться, и «дорожка 4» в новом
        релизе — это другая студия. Подпись же (`rus · MVO (LostFilm)`) переживает смену
        релиза ровно тогда, когда та же озвучка в нём есть.
        """
        want = label.casefold().strip()
        if not want:
            return None
        return next((t.index for t in self.tracks if t.label.casefold().strip() == want), None)


class TorrServer:
    """Клиент TorrServer: добавить magnet, дождаться метаданных, отдать URL потока."""

    def __init__(self, base_url: str, timeout: float = _TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session: requests.Session | None = None

    def add(self, magnet: str) -> str:
        """Добавить magnet и вернуть его hash. Метаданных на этот момент ещё нет."""
        payload = self._post("/torrents", {"action": "add", "link": magnet, "save_to_db": False})
        if not isinstance(payload, dict):
            raise InfraError("TorrServer вернул неожиданный ответ на добавление")
        torrent_hash = str(payload.get("hash", ""))
        if not torrent_hash:
            raise InfraError("TorrServer не отдал hash раздачи")
        return torrent_hash

    def warm(self, magnet: str) -> Warmup:
        """Прогрев под меню (§3.1): magnet уходит фоном и набирает пиров, пока идут вопросы."""
        warmup = Warmup(magnet=magnet)
        thread = threading.Thread(target=self._warm, args=(warmup,), daemon=True)
        warmup.thread = thread
        thread.start()
        return warmup

    def _warm(self, warmup: Warmup) -> None:
        try:
            warmup.torrent_hash = self.add(warmup.magnet)
        except InfraError as exc:  # прогрев не обязан удаться — решает основной путь
            warmup.error = exc

    def files(self, torrent_hash: str) -> list[TorrFile]:
        """Список файлов раздачи; пуст, пока метаданные не приехали по DHT."""
        payload = self._post("/torrents", {"action": "get", "hash": torrent_hash})
        if not isinstance(payload, dict):
            raise InfraError("TorrServer вернул неожиданный ответ на список файлов")
        raw = payload.get("file_stats")
        if not isinstance(raw, list):
            return []
        return [
            TorrFile(int(i.get("id") or 0), str(i.get("path", "")), int(i.get("length") or 0))
            for i in raw
            if isinstance(i, dict)
        ]

    def wait_files(self, torrent_hash: str, timeout: float = 60.0) -> list[TorrFile]:
        """Дождаться метаданных: пиры по DHT и ретрекерам (§3.1); нет за ``timeout`` — ошибка."""
        deadline = time.monotonic() + timeout
        while True:
            files = self.files(torrent_hash)
            if files:
                return files
            if time.monotonic() >= deadline:
                raise InfraError(f"раздача не отдала метаданные за {timeout:.0f} с — нет пиров")
            time.sleep(1.0)

    def stream_url(self, torrent_hash: str, index: int) -> str:
        """HTTP-URL потока конкретного файла раздачи."""
        return f"{self.base_url}/stream?link={quote(torrent_hash)}&index={index}&play"

    def drop(self, torrent_hash: str) -> None:
        """Убрать раздачу; отсутствие её ошибкой не считается."""
        with contextlib.suppress(InfraError):
            self._post("/torrents", {"action": "rem", "hash": torrent_hash})

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        import requests

        if self._session is None:
            self._session = requests.Session()
        try:
            response = self._session.post(f"{self.base_url}{path}", json=body, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise InfraError(f"TorrServer не отвечает ({self.base_url}): {why(exc)}") from exc
        except ValueError as exc:
            raise InfraError("TorrServer вернул не JSON") from exc


def probe(url: str, timeout: float = 90.0) -> Media:
    """Дорожки и длительность из HTTP-потока, не качая файл: ffprobe берёт заголовок mkv
    запросами Range — это и есть цена меню озвучек (§3).
    """
    entries = (
        "format=duration:"
        "stream=index,codec_name,codec_type,channels,width,height,bit_rate:"
        # Теги дорожки берутся ЦЕЛИКОМ, а не списком: mkvmerge пишет вес дорожки то как
        # ``BPS``, то как ``BPS-eng``/``BPS-rus`` — суффикс языковой и заранее неизвестен.
        "stream_tags"
    )
    flags = ["-v", "error", "-show_entries", entries, "-of", "json"]
    command = ["ffprobe", *flags, url]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=True)
    except FileNotFoundError as exc:
        raise InfraError("ffprobe не установлен") from exc
    except subprocess.TimeoutExpired as exc:
        raise InfraError("ffprobe не дождался потока") from exc
    except subprocess.CalledProcessError as exc:
        raise InfraError(f"ffprobe не прочитал поток: {exc.stderr.strip()[:120]}") from exc
    try:
        payload: Any = json.loads(done.stdout)
    except ValueError as exc:
        raise InfraError("ffprobe вернул не JSON") from exc
    if not isinstance(payload, dict):
        raise InfraError("ffprobe вернул не тот JSON")

    fmt = payload.get("format")
    duration = float((fmt or {}).get("duration") or 0.0) if isinstance(fmt, dict) else 0.0
    raw = payload.get("streams")
    streams = [s for s in raw if isinstance(s, dict)] if isinstance(raw, list) else []
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    video = [s for s in streams if s.get("codec_type") == "video"]
    return Media(
        duration=duration,
        tracks=tuple(_track(i, s) for i, s in enumerate(audio)),
        video=_opt_str(video[0].get("codec_name")) if video else None,
        height=int(video[0].get("height") or 0) if video else 0,
        width=int(video[0].get("width") or 0) if video else 0,
        video_bps=_video_bps(video[0], duration) if video else 0.0,
    )


def _video_bps(stream: dict[str, Any], duration: float) -> float:
    """Битрейт видеодорожки, бит/с; ``0.0`` — в паспорте его нет.

    Три источника по убыванию надёжности, и все три уже читаются тем же ffprobe:

    * тег ``BPS`` (с языковым суффиксом или без) — его пишет mkvmerge в голову mkv, то
      есть у всех релизов, собранных обычным путём («Моана 2» 14 333 020, «Тачки 3»
      14 096 894);
    * поле ``bit_rate`` потока — его отдаёт mp4/WEB-DL, где тегов mkvmerge нет вовсе;
    * ``NUMBER_OF_BYTES`` на длительность — на случай, когда mkvmerge написал вес
      дорожки, но не её битрейт.

    Не нашлось ничего — ноль, и профиль тяжести честно возвращается к слепой калибровке
    по первым выложенным сегментам (:meth:`torrcast.recode.Weights.calibrate`).
    """
    raw = stream.get("tags")
    tags: dict[str, Any] = raw if isinstance(raw, dict) else {}
    named = {str(k).upper(): v for k, v in tags.items()}
    for key, value in named.items():
        if key == "BPS" or key.startswith("BPS-"):
            with contextlib.suppress(TypeError, ValueError):
                found = float(value)
                if found > 0:
                    return found
    with contextlib.suppress(TypeError, ValueError):
        found = float(stream.get("bit_rate") or 0)
        if found > 0:
            return found
    for key, value in named.items():
        if (key == "NUMBER_OF_BYTES" or key.startswith("NUMBER_OF_BYTES-")) and duration > 0:
            with contextlib.suppress(TypeError, ValueError):
                found = float(value) * 8 / duration
                if found > 0:
                    return found
    return 0.0


def _track(index: int, stream: dict[str, Any]) -> AudioTrack:
    raw = stream.get("tags")
    tags: dict[str, Any] = raw if isinstance(raw, dict) else {}
    return AudioTrack(
        index=index,
        language=_opt_str(tags.get("language")),
        title=_opt_str(tags.get("title")),
        codec=_opt_str(stream.get("codec_name")),
        channels=int(stream.get("channels") or 0),
    )


def pick_video_file(files: list[TorrFile]) -> TorrFile:
    """Самый крупный видеофайл раздачи, он же фильм (§2.4); образ диска — :class:`InfraError`."""
    videos = [f for f in files if f.name.lower().endswith(VIDEO_EXT)]
    if not videos:
        raise InfraError(
            "в раздаче нет отдельного видеофайла (похоже на образ диска) — "
            "возьми другой релиз: cast <запрос> --release N"
        )
    return max(videos, key=lambda f: f.size)


def segment_name(slot: int) -> str:
    """Имя файла сегмента. Имя = место в фильме, а не номер по порядку упаковки — это и
    делает возможным манифест на весь фильм при упаковке по требованию (§2.1 SPEC-v2).
    """
    return f"v{slot}.ts"


def segment_slot(name: str) -> int:
    """Слот по имени файла; ``-1`` — имя не наше."""
    found = _SEGMENT_RE.fullmatch(name)
    return int(found.group(1)) if found else -1


@dataclass(frozen=True, slots=True)
class Grid:
    """Сетка сегментов: **абсолютные** границы, отсчитанные от нуля фильма.

    Это ответ на главную грабельку §6.1 SPEC-v2. Раньше сетка была не сеткой, а шагом:
    ffmpeg резал каждые N секунд от первого пакета своего прогона, а прогон начинался там,
    куда увёл ``-ss``, — то есть на опорном кадре не позже нужного места. Поэтому имя
    сегмента врало о содержимом до длины GOP, а **фаза** сетки после каждой перемотки
    становилась другой. Место фильма при одной фазе игралось чисто, при другой — вешало
    приёмник, и воспроизвести это можно было только случайно.

    Здесь граница — это число, а не «сколько прошло от старта упаковки»: сегмент ``k``
    занимает ``[bounds[k], bounds[k+1])`` всегда, с какого бы места ни начали паковать.
    Ровно этот список идёт и в манифест (``EXTINF`` = фактическая длина куска), и в
    команду ffmpeg (:func:`ffmpeg_pack_command`), так что манифест и нарезка — одно и то же.

    Границы стоят на **опорных кадрах**, когда карта их известна (:mod:`torrcast.keymap`):
    тогда каждый сегмент декодируется сам по себе, и перемотка в любую точку показывает
    картинку сразу, а не с ближайшего опорного кадра где-то в середине куска. Нет карты —
    ровная сетка по :data:`HLS_SEGMENT_SECONDS`, как было.
    """

    #: Начала сегментов, секунды от начала фильма; ``bounds[0]`` всегда 0.
    bounds: tuple[float, ...]
    duration: float
    #: Границы стоят на опорных кадрах — сегменты самостоятельны.
    on_keys: bool = False

    @classmethod
    def uniform(cls, duration: float, step: float = HLS_SEGMENT_SECONDS) -> Grid:
        """Ровная сетка: каждые ``step`` секунд от нуля фильма.

        Хвост короче половины шага отдельным сегментом не делается — он прилипает к
        последнему: пара секунд в манифесте лишним куском не стоит. Кино короче шага —
        один сегмент на всё, и длительность остаётся честной: приписать ему лишние
        секунды значило бы пообещать приёмнику то, чего в файле нет.
        """
        length = max(duration, 0.0)
        count = max(1, math.ceil((length - step / 2) / step))
        return cls(tuple(step * k for k in range(count)), length, False)

    @classmethod
    def on_keyframes(
        cls,
        keys: Sequence[float],
        duration: float,
        step: float = HLS_SEGMENT_SECONDS,
        sizes: Sequence[int] = (),
        extra_mbit: float = 0.0,
        ceiling_mbit: float = 0.0,
        cap: float = MAX_SEGMENT_BYTES,
    ) -> Grid:
        """Сетка по опорным кадрам: следующая граница — первый опорный кадр не раньше,
        чем через ``step`` секунд после предыдущей, **и не тяжелее** :data:`MAX_SEGMENT_BYTES`.

        Длина сегмента получается от ``step`` до ``step + GOP``: на «Моане» 2016
        (GOP до 4.96 с) это 10.0–14.9 с, на «Моане 2» (GOP до 11.5 с) — до 21.5 с.
        Короче ``step`` в середине фильма сегментов не бывает — иначе на сценах-вспышках
        (24 опорных кадра за полсекунды) манифест распух бы на пустом месте. Хвост —
        исключение: он такой, какой остался, но не короче половины шага.

        **Потолок байт** (§6.2.4 SPEC-v2) — вторая половина правила, и она главная:
        приёмник Q70D срывается в BUFFERING на сегменте тяжелее ~19 МБ, сколько бы секунд
        в нём ни было. Поэтому граница берётся так: первый опорный кадр не раньше ``step``,
        **если** предсказанный вес куска влезает в ``cap``; не влезает — последний кадр,
        который влезает (кусок получается короче ``step``, и это дешевле подвиса); не влезает
        ни один — первый кадр, что есть (резать GOP нельзя, и врать об этом не будем).

        Вес предсказывается из той же карты, из которой строится профиль тяжести
        (:class:`torrcast.recode.Weights`): ``sizes`` — смещения опорных кадров в файле,
        ``extra_mbit`` — что в контейнере есть, а на ТВ не уезжает (лишние дорожки и
        субтитры), ``ceiling_mbit`` — потолок перекодирования (§6.2): тяжёлый кусок уедет
        не тяжелее него. Карты смещений нет (кэш прошлой версии, чужой контейнер) — правило
        вырождается в прежнее «первый кадр не раньше ``step``».
        """
        weigh = _weigher(keys, sizes, extra_mbit, ceiling_mbit)
        bounds = [0.0]
        limit = duration - step / 2
        index = 0
        while True:
            prev = bounds[-1]
            index = bisect.bisect_right(keys, prev, lo=index)
            fits = first = None
            for key in keys[index:]:
                if key >= limit:
                    break
                if weigh(prev, key) <= cap:
                    fits = key
                if key >= prev + step:
                    first = key
                    break
            if first is None:
                break  # дальше только хвост короче половины шага — он прилипает к последнему
            if weigh(prev, first) <= cap or fits is None:
                bounds.append(first)  # влез — или один GOP тяжелее потолка, резать нечем
            else:
                bounds.append(fits)
        return cls(tuple(bounds), duration, True)

    @property
    def count(self) -> int:
        return len(self.bounds)

    def start(self, slot: int) -> float:
        """Начало сегмента, секунды от начала фильма."""
        return self.bounds[min(max(slot, 0), self.count - 1)]

    def end(self, slot: int) -> float:
        """Конец сегмента: начало следующего, а у последнего — конец фильма."""
        return self.bounds[slot + 1] if 0 <= slot + 1 < self.count else self.duration

    def span(self, slot: int) -> float:
        return self.end(slot) - self.start(slot)

    def slot_at(self, seconds: float) -> int:
        """Номер сегмента, в который попадает секунда фильма."""
        return max(0, bisect.bisect_right(self.bounds, max(seconds, 0.0)) - 1)

    def target(self) -> int:
        """``EXT-X-TARGETDURATION``: округлённая вверх длина самого длинного сегмента."""
        return max(1, math.ceil(max(self.span(k) for k in range(self.count))))

    def manifest(self) -> str:
        """Манифест VOD на **весь фильм**: все сегменты сетки и ``ENDLIST``.

        Это и есть ответ на §2.1 SPEC-v2. Приёмнику неоткуда узнать длительность, кроме
        манифеста: у скользящего live-плейлиста её нет вовсе, поэтому ТВ считал показ
        эфиром и не давал ни таймлайна, ни перемотки. Здесь длительность — сумма
        ``EXTINF``, то есть ровно длина фильма, и перемотка разрешена в любую его точку.

        Манифест **статический**: он не зависит от того, что упаковано прямо сейчас, и
        перечисляет сегменты, которых на диске ещё нет. Целый фильм в tmpfs не влезает —
        но приёмнику и не нужен файл раньше, чем он его попросит: за это отвечает
        :class:`Feed`, которая на запрос неупакованного места пакует оттуда.

        Проверено на живом Q70D 05-08-2026: ``duration`` в MEDIA_STATUS = длине манифеста,
        ``seek`` в произвольную точку отрабатывает за доли секунды и показ продолжается.
        """
        lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            f"#EXT-X-TARGETDURATION:{self.target()}",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXT-X-PLAYLIST-TYPE:VOD",
        ]
        if self.on_keys:
            # Не украшение: каждый сегмент начинается с опорного кадра, и приёмнику
            # разрешено начать показ с любого — на этом и держится перемотка (§2.1).
            lines.append("#EXT-X-INDEPENDENT-SEGMENTS")
        for slot in range(self.count):
            lines += [f"#EXTINF:{self.span(slot):.6f},", segment_name(slot)]
        lines.append("#EXT-X-ENDLIST")
        return "\n".join(lines) + "\n"


def _weigher(
    keys: Sequence[float], sizes: Sequence[int], extra_mbit: float, ceiling_mbit: float
) -> Callable[[float, float], float]:
    """Предсказатель веса куска ``[a, b)`` в байтах — тот же расчёт, что у профиля тяжести.

    Карта даёт байты **контейнера**: у «Моаны 2» это десять озвучек и восемь субтитров
    сверх картинки. На ТВ уезжает видео плюс наш AAC, поэтому из битрейта вычитается
    ``extra_mbit`` (:class:`torrcast.recode.Weights` считает ту же поправку), а тяжёлый
    кусок ещё и перекодируется — выше ``ceiling_mbit`` он не уедет при всём желании.

    Карты смещений нет — вес неизвестен, и предсказатель честно отдаёт ноль: правило
    потолка тогда не срабатывает ни разу, а сетка остаётся прежней.
    """
    if len(sizes) != len(keys) or len(keys) < 2:
        return lambda a, b: 0.0

    def weigh(a: float, b: float) -> float:
        span = b - a
        if span <= 0:
            return 0.0
        head = bisect.bisect_right(keys, a + SPLIT_SLACK) - 1
        tail = bisect.bisect_right(keys, b + SPLIT_SLACK) - 1
        head = min(max(head, 0), len(sizes) - 1)
        tail = min(max(tail, 0), len(sizes) - 1)
        mbit = max(0.0, (sizes[tail] - sizes[head]) * 8 / span / 1e6 - extra_mbit)
        if ceiling_mbit > 0:
            mbit = min(mbit, ceiling_mbit)
        return mbit * span * 1e6 / 8

    return weigh


def _keys_cache(source_url: str) -> Path:
    """Где лежит снятая карта опорных кадров этого файла.

    Ключ — сам URL потока: в нём hash раздачи и номер файла, то есть ровно то, что
    определяет содержимое. Кэш нужен не ради экономии трафика (4 МБ), а ради времени:
    Cues лежат в хвосте файла, и **первое** чтение этого места стоит роя — замерено
    06-08-2026 на стенде, 13.8 с на «Моане» 2016 и 24.4 с на «Моане 2». Второй показ
    того же файла (продолжение с середины — обычное дело) платить это не должен.
    """
    from torrcast.state import state_path

    return (
        state_path().parent / "keys" / f"{hashlib.sha1(source_url.encode()).hexdigest()[:16]}.json"
    )


class FilmKeys(NamedTuple):
    """Карта опорных кадров файла в том виде, в каком ей пользуется показ.

    ``at`` — времена от начала фильма, по ним строится сетка (:class:`Grid`).
    ``offset`` — где эти кадры лежат в файле; по ним греется рой под перемотку и под
    продолжение с середины (:func:`warm_at`, §7.2 SPEC-v2). Списки одной длины, и порядок
    у них общий: ``at[k]`` лежит на ``offset[k]``.
    """

    duration: float
    at: list[float]
    offset: list[int]
    #: Контейнер файла, ``mkv`` или ``mp4``. Пусто — карта из кэша прошлой версии.
    kind: str = ""

    def byte_at(self, seconds: float) -> int:
        """Смещение опорного кадра не позже ``seconds``; карта без смещений — ``0``.

        Не позже, а не «ближайший»: показ с этого места и начнёт читать, потому что
        ffmpeg с ``-ss`` встаёт на опорный кадр не позже запрошенного (§6.0 SPEC-v2).
        """
        if not self.offset:
            return 0
        found = bisect.bisect_right(self.at, max(seconds, 0.0)) - 1
        return self.offset[min(max(found, 0), len(self.offset) - 1)]


def _read_keys(cache: Path) -> FilmKeys | None:
    with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
        saved = json.loads(cache.read_text("utf-8"))
        at = [float(x) for x in saved["keys"]]
        # Кэш прошлой версии смещений не знал: он всё ещё годен для сетки, а грелка
        # позиции без смещений просто не работает — это лучше, чем выбросить карту.
        return FilmKeys(
            float(saved["duration"]),
            at,
            [int(x) for x in saved.get("bytes", ())],
            str(saved.get("kind", "")),
        )
    return None


def _fetching(lock: Path) -> bool:
    """Карту прямо сейчас снимает кто-то другой (прогрев под меню — соседний процесс)."""
    with contextlib.suppress(OSError):
        return time.time() - lock.stat().st_mtime < KEYS_LOCK
    return False


def film_keys(source_url: str) -> FilmKeys:
    """Карта опорных кадров видео: из кэша или из индекса контейнера (:mod:`torrcast.keymap`).

    Если карту уже снимает прогрев (:func:`warm_file`), ждём его, а не читаем индекс
    файла вторым потоком: рой от этого быстрее не станет, а старт показа удвоится.
    """
    from torrcast.keymap import keyframes, video_track

    cache = _keys_cache(source_url)
    if (ready := _read_keys(cache)) is not None:
        mark("карта: из кэша")
        return ready
    lock = cache.with_suffix(".lock")
    deadline = time.monotonic() + KEYS_WAIT
    waited = time.monotonic()
    while _fetching(lock) and time.monotonic() < deadline:
        time.sleep(0.2)
        if (ready := _read_keys(cache)) is not None:
            mark("карта: дождались прогрева", ждали=round(time.monotonic() - waited, 2))
            return ready
    with contextlib.suppress(OSError):
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.touch()
    mark("карта: чтение")
    # ⚠️ Замок снимается не после чтения, а после **записи кэша**: между ними лежит разбор
    # карты, и сосед, отпущенный раньше времени, кэша ещё не увидит и полезет читать хвост
    # сам. Ровно так холодный старт платил разбор дважды (замер 06-08-2026: CLI и юнит
    # разбирали одну и ту же карту параллельно).
    try:
        found = keyframes(source_url)
        mark("карта: снята", кадров=len(found.points), байт=found.taken)
        # ⚠️ Дорожку видео выбираем ОДИН раз. Пока этот вызов стоял внутри списка, он
        # считался на каждую точку Cues, а сам он линейный по всем точкам — то есть карта
        # разбиралась квадратично. Цена замерена 06-08-2026 на стенде: «Моана 2», 7274
        # точки — 18.5 с чистого процессора после того, как рой всё отдал. Ровно это и
        # принимали за «первое чтение хвоста у холодного роя» (§7.1 SPEC-v2): рой отдаёт
        # Cues за 2–6 с, остальное было наше.
        track = video_track(found.points)
        video = [p for p in found.points if p.track == track]
        ready = FilmKeys(
            found.duration, [p.at for p in video], [p.offset for p in video], found.kind
        )
        with contextlib.suppress(OSError):
            cache.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache.with_suffix(".tmp")
            body = {
                "duration": ready.duration,
                "keys": ready.at,
                "bytes": ready.offset,
                "kind": ready.kind,
            }
            tmp.write_text(json.dumps(body), "utf-8")
            tmp.replace(cache)
    finally:
        with contextlib.suppress(OSError):
            lock.unlink(missing_ok=True)
    return ready


def warm_at(source_url: str, offset: int, upto: int = HEAD_WARM, alive: Any = None) -> int:
    """Протянуть через рой кусок файла с ``offset`` и выбросить: нужен прогретый кэш.

    Показ читает файл ровно двумя местами: начало (заголовок контейнера, а с ним и
    ``moov`` у mp4) и то место, откуда пойдёт картинка. Пока этих байт нет в кэше
    TorrServer, ffmpeg ждёт рой, а показ ждёт ffmpeg. Под меню и под вопросом
    «Продолжить?» они берутся бесплатно по времени: человек в этот момент отвечает.
    Лишнего трафика тут нет — ровно эти байты показ прочитает следующим действием.

    ``alive`` — жив ли ещё смысл греть: релиз, от которого показ отказался, дотягивать
    нельзя, он отъедает полосу у выбранного (:meth:`torrcast.cli._Bench.keep_only`).
    """
    began = time.monotonic()
    taken = 0
    where = f"bytes={offset}-{offset + upto - 1}"
    request = urllib.request.Request(source_url, headers={"Range": where})
    with urllib.request.urlopen(request, timeout=WARM_TIMEOUT) as answer:
        while chunk := answer.read(1 << 20):
            taken += len(chunk)
            if alive is not None and not alive():
                break
    mark("прогрето", смещение=offset, байт=taken, за=round(time.monotonic() - began, 2))
    return taken


def pull_head(source_url: str, upto: int = HEAD_WARM, alive: Any = None) -> int:
    """Прогреть начало файла — частный случай :func:`warm_at` со смещением ноль."""
    return warm_at(source_url, 0, upto, alive)


def head_open(kind: str) -> int:
    """Сколько головы греть под продолжение с середины: у mkv её мало, у mp4 там ``moov``."""
    return HEAD_OPEN.get(kind, HEAD_OPEN_DEFAULT)


def container_of(name: str) -> str:
    """Контейнер по имени файла раздачи; чужое расширение — пустая строка.

    Нужно ровно для одного: карта, снятая прошлой версией, лежит в кэше без контейнера, и
    без этой подсказки продолжение по такому фильму грело бы восемь мегабайт головы до
    конца времён. Имя файла у показа под рукой всегда — оно приезжает вместе со списком
    раздачи, — а сам URL потока имени не несёт (в нём hash и номер файла).
    """
    tail = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if tail in {"mkv", "webm"}:
        return "mkv"
    return "mp4" if tail in {"mp4", "m4v", "mov"} else ""


def warm_file(source_url: str, at: float = 0.0, alive: Any = None, name: str = "") -> None:
    """Прогреть файл фоном: карта опорных кадров, начало потока и место, откуда играем.

    Зовётся с самой ранней секунды, когда известен файл, — пока человек отвечает на
    вопросы (§4 SPEC-v2). Порядок именно такой: без карты показ не построит сетку и не
    запустит ffmpeg вовсе; начало файла нужно ffmpeg, чтобы вообще открыть вход; а место
    ``at`` — это то, что он прочитает третьим. Не вышло — не беда: показ сделает то же
    самое сам, просто на своём времени.

    ``at > 0`` — продолжение с середины (§7.2 SPEC-v2). Там начало файла нужно только на
    заголовок, поэтому его берём куском поменьше (:data:`HEAD_OPEN`, размер зависит от
    контейнера), а основной прогрев уходит туда, где лежит позиция: байтовое смещение
    известно из той же карты.
    """

    def work() -> None:
        keys: FilmKeys | None = None
        with contextlib.suppress(Exception):
            keys = film_keys(source_url)
        if alive is not None and not alive():
            return
        offset = keys.byte_at(at) if keys is not None and at > 0 else 0
        # Контейнер знает карта; у карты из кэша прошлой версии его нет — тогда спрашиваем
        # имя файла раздачи, оно у показа всегда под рукой.
        head = head_open((keys.kind if keys is not None else "") or container_of(name))
        with contextlib.suppress(Exception):
            pull_head(source_url, head if offset else HEAD_WARM, alive)
        if not offset:
            return
        with contextlib.suppress(Exception):
            if alive is None or alive():
                warm_at(source_url, offset, HEAD_WARM, alive)

    threading.Thread(target=work, daemon=True).start()


def grid_for(
    source_url: str,
    duration: float,
    step: float = HLS_SEGMENT_SECONDS,
    on_keys: bool = True,
    say: Any = None,
    delivered_mbit: float = 0.0,
    ceiling_mbit: float = 0.0,
) -> Grid:
    """Сетка для конкретного файла: по опорным кадрам, если карту удалось снять.

    Карта берётся двумя-тремя Range-запросами из индекса контейнера
    (:func:`torrcast.keymap.keyframes`) и стоит около секунды. Контейнер незнакомый, индекса
    в нём нет, карта не похожа на видео — берём ровную сетку и говорим об этом вслух:
    молчаливая подмена нарезки — ровно то, из-за чего §6 SPEC-v2 расследовали двое суток.

    ``delivered_mbit`` — сколько Мбит/с уедет на ТВ в среднем по фильму (паспорт ffprobe,
    :attr:`Media.delivered_mbit`), ``ceiling_mbit`` — потолок перекодирования
    (:attr:`torrcast.state.Config.recode_mbit`, ноль — перекодирование выключено). Из них
    считается поправка «контейнер → ТВ» и работает потолок веса сегмента
    (:data:`MAX_SEGMENT_BYTES`) — без них правило потолка вырождается в прежнее.
    """
    began = time.monotonic()
    if not on_keys:
        if say:
            say(f"сетка ровно по {step:g} с — так велено настройкой")
        return Grid.uniform(duration, step)
    try:
        found = film_keys(source_url)
    except InfraError as exc:
        if say:
            say(f"сетка ровно по {step:g} с: {exc}")
        return Grid.uniform(duration, step)
    length = duration or found.duration
    if len(found.at) < 3 or found.at[-1] < length * 0.5:
        if say:
            say(f"сетка ровно по {step:g} с: карта опорных кадров не похожа на видео")
        return Grid.uniform(length, step)
    grid = Grid.on_keyframes(
        found.at,
        length,
        step,
        sizes=found.offset,
        extra_mbit=_extra_mbit(found, delivered_mbit),
        ceiling_mbit=ceiling_mbit,
    )
    if say:
        spans = [grid.span(k) for k in range(grid.count)]
        say(
            f"сетка по опорным кадрам: {grid.count} сегментов по {min(spans):.1f}–"
            f"{max(spans):.1f} с, не тяжелее {MAX_SEGMENT_BYTES / 1e6:.0f} МБ "
            f"(карта за {time.monotonic() - began:.1f} с)"
        )
    return grid


def _extra_mbit(keys: FilmKeys, delivered_mbit: float) -> float:
    """Что в контейнере есть, а на ТВ не уезжает, Мбит/с — по карте и паспорту.

    Ровно то же число, что набирает :meth:`torrcast.recode.Weights.calibrate` по факту, но
    известное до первого куска. Паспорт молчит (mp4 без тегов) — ноль: тогда потолок веса
    считает по контейнеру целиком, то есть режет с запасом. Запас безопасен, недооценка нет.
    """
    if delivered_mbit <= 0 or len(keys.offset) != len(keys.at) or len(keys.at) < 3:
        return 0.0
    span = keys.at[-1] - keys.at[0]
    if span <= 0:
        return 0.0
    container = (keys.offset[-1] - keys.offset[0]) * 8 / span / 1e6
    return max(0.0, container - delivered_mbit)


def pack_start(source_url: str, at: float, timeout: float = PILOT_TIMEOUT) -> float:
    """Куда на самом деле встанет ffmpeg после ``-ss at``: пробный прогон в один кадр.

    Знать это обязательно, и вычислить нельзя. Сетка сегментного муксера отсчитывается от
    **первого пакета прогона**, а ``-ss`` уводит ffmpeg на опорный кадр не позже
    запрошенного места — причём не обязательно на ближайший: замерено 05-08-2026 на
    «Моане» 2016, ``-ss 66.150`` (сама граница — опорный кадр) даёт первый кадр 62.688, то
    есть **через один**. Поэтому место старта не угадывают, а измеряют: тот же ffmpeg, тот
    же ``-ss``, один кадр на выход. Цена — 0.5–1.7 с и пара мегабайт (замер на стенде).

    ``-muxdelay 0 -muxpreload 0`` обязательны: без них мультиплексор mpegts добавляет
    к меткам свои 1.4 с, и «первый кадр» оказался бы не там, где он есть на самом деле.
    """
    if at <= 0:
        return 0.0
    with tempfile.TemporaryDirectory(prefix="torrcast-pilot-") as tmp:
        probe_path = f"{tmp}/first.ts"
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-copyts", "-ss", f"{at:.3f}",
            "-i", source_url, "-map", "0:v:0", "-c", "copy", "-frames:v", "1",
            "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", "-y", probe_path,
        ]  # fmt: skip
        try:
            subprocess.run(command, capture_output=True, timeout=timeout, check=True)
            found = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                 "packet=pts_time", "-of", "csv=p=0", "-read_intervals", "%+#1", probe_path],
                capture_output=True, text=True, timeout=timeout, check=True,
            )  # fmt: skip
        except (OSError, subprocess.SubprocessError):
            return at  # не вышло — считаем, что встали ровно на границе, и скажем об этом
        head = found.stdout.strip().splitlines()
        try:
            return float(head[0].split(",")[0])
        except (IndexError, ValueError):
            return at


def ffmpeg_pack_command(
    source_url: str,
    audio_index: int,
    run_dir: str,
    grid: Grid,
    slot: int,
    at: float,
    readrate: float = 1.0,
    burst: float = 0.0,
    encode: Any = None,
    until: int = -1,
) -> list[str]:
    """Команда ffmpeg: паковать фильм по сетке ``grid``, начиная с сегмента ``slot``.

    ``at`` — где прогон встанет на самом деле (:func:`pack_start`). Всё держится на трёх
    вещах:

    * ``-f segment -segment_times`` вместо ``-f hls -hls_time``. Сегментный муксер умеет
      получить **список** мест реза, а не один шаг, — и это единственный способ положить
      границы туда, где они стоят в манифесте. Список считается от ``at``, потому что
      муксер сравнивает метки с начала прогона, а не с начала фильма.
    * ``-copyts`` **вместе с** ``-muxdelay 0 -muxpreload 0`` — метки времени остаются
      исходными, то есть абсолютным временем фильма. Без ``-copyts`` ffmpeg сбрасывает их
      в ноль на каждом ``-ss``, и приёмник после перепаковки показывал бы позицию от
      начала куска, а не от начала фильма. А одного ``-copyts`` мало: мультиплексор
      mpegts по умолчанию сдвигает ВСЕ метки вперёд на ``muxdelay + muxpreload`` = **1.4 с**
      (:data:`MPEGTS_MUX_DELAY`), и «время фильма» в сегментах оказывалось не временем
      фильма. Цена этой мелочи — двое суток чужого расследования (§6.2.2 SPEC-v2): карту
      опорных кадров сверяли с метками готовых сегментов, видели ровно +1.400 с на каждой
      границе и записали это в «карта врёт про этот релиз». Карта не врала — врал муксер,
      и :func:`pack_start` эти же два флага ставил с самого начала, то есть пробный прогон
      мерил время фильма, а настоящий писал время фильма плюс 1.4 с.
    * ``-break_non_keyframes`` — резать ли посреди GOP. На сетке по опорным кадрам этого
      не нужно и нельзя: муксер сам дождётся опорного кадра, и граница встанет ровно туда,
      куда обещал манифест. На ровной сетке — наоборот, иначе куски разъедутся с сеткой.

    Прогон почти всегда начинается раньше своей границы: ``-ss`` уводит на опорный кадр
    раньше. Эта докатка уходит в отдельный сегмент с номером ``slot - 1``, который
    :meth:`Packer.publish` выбрасывает, — так наружу попадает только то, что совпадает
    с манифестом, и чужой сегмент не затирается.

    Темп упаковки (§6 SPEC-v2) держится **одним ffmpeg'ом и без пауз процесса**:

    * ``-readrate 1`` — читать вход со скоростью реального времени. Придержать упаковку
      сигналом (SIGSTOP) больше не нужно: она сама не убегает дальше ``burst``.
    * ``-readrate_initial_burst`` (ffmpeg ≥ 6.1) — первые ``burst`` секунд читаются на
      полной скорости. Без него ``readrate 1`` дважды вреден: приёмник идёт вровень с
      упаковкой и буферится на каждом стыке, а после перемотки ему разом нужны шесть
      сегментов (замерено на Q70D: v50…v55 за одну секунду).

    Отставание ffmpeg наверстывает сам: его планка — ``wallclock * readrate + burst``, и
    пока текущий dts ниже планки, он читает на полной скорости (``readrate_sleep`` в
    fftools). То есть просадка роя лечится без нашего участия, а запас впереди приёмника
    остаётся ограниченным ``burst`` — ровно поэтому tmpfs не растёт без предела.

    ``encode`` (:class:`torrcast.recode.Encode`) заменяет ``-c:v copy`` перекодированием
    тяжёлого куска (§6.2). Всё остальное — сетка, метки, границы, звук — остаётся тем же,
    иначе стык копии с перекодом приёмник бы заметил.

    ⚠️ У перекодирующего прогона **докатки нет**: ``-ss`` при перекодировании точен, лишние
    кадры декодируются и выбрасываются, так что первый пакет стоит ровно на границе. Звать
    для него :func:`pack_start` не надо (и вредно: измеренный ``at`` уведёт весь прогон на
    сегмент назад).

    ``until`` ограничивает прогон сегментом с этим номером — кодировщик работает заходами
    по несколько кусков, чтобы перемотка успевала переприоритезировать очередь.
    """
    run = run_dir.rstrip("/")
    behind = encode is None and at < grid.start(slot) - SPLIT_SLACK  # прогон начался раньше границы
    first = slot if behind else slot + 1
    upto = grid.count if until < 0 else min(until + 2, grid.count)
    times = ",".join(f"{grid.start(k) - at:.3f}" for k in range(first, upto))
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning"]
    if readrate > 0:
        command += ["-readrate", f"{readrate:g}"]
        if burst > 0:
            command += ["-readrate_initial_burst", f"{burst:g}"]
    command += ["-copyts"]
    if slot > 0:
        command += ["-ss", f"{grid.start(slot):.3f}"]
    command += ["-i", source_url, "-map", "0:v:0", "-map", f"0:a:{audio_index}"]
    command += ["-c:v", "copy"] if encode is None else encode.args(grid, slot, upto - 2)
    if until >= 0:
        # ``-to`` при ``-copyts`` считается в абсолютном времени фильма — том же, что в
        # сетке. Без ограничения заход кодировщика доехал бы до конца фильма.
        command += ["-to", f"{grid.end(until) + 1.0:.3f}"]
    command += (
        f"-c:a {AUDIO_CODEC} -ac {AUDIO_CHANNELS} -b:a {AUDIO_BITRATE} "
        f"-muxdelay 0 -muxpreload 0 "
        f"-f segment -segment_format mpegts -segment_time_delta {SPLIT_SLACK:g} "
        f"-break_non_keyframes {0 if grid.on_keys else 1} "
        f"-segment_start_number {slot - 1 if behind else slot} "
        f"-segment_list {run}/{PACK_LIST} -segment_list_type csv -segment_list_flags +live"
    ).split()
    if times:
        command += ["-segment_times", times]
    command.append(f"{run}/v%d.ts")
    return command


def parse_manifest(text: str) -> tuple[list[tuple[str, float]], bool]:
    """Манифест → пары (сегмент, длительность) и признак конца (``#EXT-X-ENDLIST``)."""
    segments: list[tuple[str, float]] = []
    seconds = 0.0
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#EXTINF:"):
            with contextlib.suppress(ValueError):
                seconds = float(line[8:].split(",")[0])
        elif line and not line.startswith("#"):
            segments.append((line, seconds))
    return segments, "#EXT-X-ENDLIST" in text


def hls_dir(path: str) -> Path:
    """Чистый каталог сегментов. Это tmpfs: фильм на диск не пишем (§3, §1)."""
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    for junk in (*directory.glob("v*.ts"), *directory.glob("*.m3u8")):
        junk.unlink(missing_ok=True)
    forget_playing(directory)  # флажок прошлого показа картинку нового не доказывает
    return directory


def playing_flag(out: Path) -> Path:
    """Путь флажка «картинка на экране» (:data:`PLAYING_FLAG`)."""
    return out / PLAYING_FLAG


def mark_playing(out: Path) -> None:
    """Показ увидел ``PLAYING``: с этой секунды на экране есть изображение (§4 SPEC-v2)."""
    with contextlib.suppress(OSError):
        playing_flag(out).touch()


def forget_playing(out: Path) -> None:
    """Убрать флажок: следующий показ обязан доказать картинку заново."""
    with contextlib.suppress(OSError):
        playing_flag(out).unlink(missing_ok=True)


@dataclass(slots=True)
class Packer:
    """Один прогон упаковки: процесс ffmpeg, который пакует фильм с сегмента ``first``.

    ffmpeg пишет в свой каталог (:data:`PACK_DIR`), наружу сегменты выкладывает
    :meth:`publish` переименованием. Так решаются сразу две вещи: наружу не попадает
    недописанный кусок и не затирается чужой (см. :data:`PACK_DIR`).
    """

    proc: subprocess.Popen[bytes]
    out: Path
    #: Каталог этого прогона: сюда ffmpeg кладёт куски, включая мусорную докатку.
    run: Path
    #: С какого сегмента сетки начат этот прогон: всё, что раньше, паковал не он.
    first: int = 0
    #: **Честный край прогона**: последний сегмент, который ЭТОТ прогон выложил наружу
    #: (:meth:`publish`). ``first - 1`` — не выложено ещё ничего.
    #:
    #: Ровно это число, а не глоб каталога (:meth:`frontier`), отвечает на вопрос «кусок
    #: вот-вот допакуется или его не будет вовсе» (:meth:`Feed._steer`). Разница не
    #: теоретическая: в каталоге показа лежат и куски прошлых прогонов — сетка одна на
    #: весь показ, поэтому они честные и отдаются приёмнику, — но к тому, докуда дошёл
    #: текущий прогон, они отношения не имеют. Глоб путал одно с другим в обе стороны:
    #: «край» уезжал вперёд на чужие куски (запрос далеко назад считался ожиданием и
    #: висел до 404) и назад на свежий каталог (замер 06-08-2026: 20 ложных перезапусков
    #: за 100 с показа). Здесь край растёт только там, где мы сами переименовали файл.
    edge: int = -1
    log: Any = None
    #: Упаковку погасили намеренно (пауза на пульте) — смерть процесса не авария.
    halted: bool = False
    #: Зачем мы сами сняли этот прогон (:meth:`stop`); пусто — мы его не трогали.
    #:
    #: ⚠️ Без этой строки собственный ``terminate`` неотличим от аварии: ffmpeg по SIGTERM
    #: выходит **кодом 255** (положительным!), а «Exiting normally, received signal 15» он
    #: пишет уровнем ``info``, то есть при нашем ``-loglevel warning`` не пишет ничего.
    #: Ровно так и родился 🔴 «первый прогон следующей серии умирает молча» (§7.4
    #: SPEC-v2): показ ругался на труп, который сам же и снял.
    stopped: str = ""
    #: Обрыв ЭТОГО прогона уже посчитан (:meth:`Feed._survive`).
    blamed: bool = False
    #: Каталог перекодированных кусков (§6.2). Если для слота там лежит готовый кусок,
    #: наружу идёт он, а копия выбрасывается: место в фильме и метки те же, а битрейт
    #: такой, который приёмник гарантированно тянет.
    #:
    #: Выкладка остаётся ровно здесь, вторым выкладывающим кодировщик не становится —
    #: иначе инвариант «край двигает только состоявшееся переименование» (:attr:`edge`,
    #: §7.4 SPEC-v2) пришлось бы держать в двух местах.
    spare: Path | None = None
    #: Кого позвать, когда сегмент ушёл наружу: ``(слот, перекодирован ли)``.
    told: Any = None
    #: Последний сегмент, который этому прогону разрешено выложить; ``-1`` — без предела.
    #:
    #: ⚠️ Нужно ровно кодировщику и ровно против ОБРЕЗКА. Заход кодировщика ограничен
    #: ``-to`` с запасом в секунду (:func:`ffmpeg_pack_command`), и на этот запас муксер
    #: успевает открыть СЛЕДУЮЩИЙ файл — в нём остаётся секунда фильма вместо десяти.
    #: Дальше этот огрызок лежал в :data:`torrcast.recode.RECODE_DIR` как готовый кусок и
    #: выкладывался наружу вместо честной копии: живой Q70D 06-08-2026 на «Тачках 3» —
    #: ``v311`` 1.3 МБ вместо 11 МБ, приёмник встал на 8 с и потерял 8 секунд фильма.
    #: У «Моаны 2» это не всплывало: там тяжелы почти все куски подряд, и огрызок всегда
    #: успевал смениться настоящим перекодом следующего захода.
    last: int = -1
    #: Когда прогон начался (``time.monotonic``) и с какой секунды ФИЛЬМА ffmpeg читает
    #: вход (``-ss``, то есть с учётом докатки). Вместе с :attr:`rate` и :attr:`burst` это
    #: и есть планка чтения ffmpeg, по которой считается :meth:`eta`.
    began: float = 0.0
    at: float = 0.0
    #: ``-readrate`` и ``-readrate_initial_burst`` этого прогона; ноль — читаем без темпа.
    rate: float = 0.0
    burst: float = 0.0
    #: Кого спросить «этот кусок сейчас перекодируют, подожди»: ``(слот, вес копии) -> bool``.
    #:
    #: Нужно ровно против одной гонки, найденной живым прогоном (§6.2): упаковщик на
    #: старте прогона выкладывает ``burst`` (60 с) разом, а кодировщику на эти же 60 с
    #: нужно вдвое меньше, но не мгновение, — и тяжёлые куски уходили копией просто
    #: потому, что упаковщик их обогнал. Придержанный кусок никуда не девается: он лежит
    #: в каталоге прогона и выложится либо перекодированным, либо как есть по истечении
    #: срока. Ждать при этом безопасно только там, докуда показу ещё далеко, — за этим
    #: следит спрашиваемый (:meth:`torrcast.recode.Recoder.holding`).
    hold: Any = None

    def __post_init__(self) -> None:
        # Прогон, который ещё ничего не выложил, стоит ровно перед своим первым сегментом:
        # так «край» и «ниже края» осмысленны с первой же секунды, до всякого publish.
        self.edge = max(self.edge, self.first - 1)

    @classmethod
    def start(
        cls,
        command: list[str],
        out: Path,
        run: Path,
        first: int = 0,
        spare: Path | None = None,
        told: Any = None,
        hold: Any = None,
        last: int = -1,
        at: float = 0.0,
        rate: float = 0.0,
        burst: float = 0.0,
    ) -> Packer:
        log = tempfile.TemporaryFile()  # noqa: SIM115 — живёт всё воспроизведение
        shutil.rmtree(run, ignore_errors=True)
        run.mkdir(parents=True, exist_ok=True)
        began = time.monotonic()
        try:
            proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log)
        except FileNotFoundError as exc:
            raise InfraError("ffmpeg не установлен") from exc
        return cls(
            proc=proc,
            out=out,
            run=run,
            first=first,
            log=log,
            spare=spare,
            told=told,
            hold=hold,
            last=last,
            began=began,
            at=at,
            rate=rate,
            burst=burst,
        )

    def eta(self, film: float) -> float:
        """Через сколько секунд ffmpeg дочитает вход до секунды ``film``. Оценка снизу.

        Считается по собственной планке ffmpeg, а не по нашим наблюдениям: с
        ``-readrate R -readrate_initial_burst B`` он читает всё, что ниже
        ``-ss + B + прошло * R``, на полной скорости, а выше — ровно в темпе ``R``
        (``readrate_sleep`` в ``ffmpeg.c``). Значит место ``film`` он тронет не раньше, чем
        через ``(film - планка) / R``.

        Оценка **снизу** намеренно: реальный прогон может отставать и от планки (холодный
        рой, слабый процессор), и тогда ждать придётся дольше. Но решение, которое на ней
        строится, — «перезапустить упаковку с этого места» (:meth:`Feed._steer`), а
        перезапуск лечит ровно упирание в темп и ничем не помогает отставанию по входу.
        Поэтому недооценка тут безопасна, а переоценка стоила бы лишних перезапусков.

        ``rate <= 0`` — темпа нет, ffmpeg читает во весь опор: ждать нечего, ноль.
        """
        if self.rate <= 0:
            return 0.0
        reach = self.at + self.burst + (time.monotonic() - self.began) * self.rate
        return max(0.0, (film - reach) / self.rate)

    def publish(self) -> None:
        """Выложить наружу куски, которые ffmpeg уже дописал.

        Дописан тот, за которым появился следующий: сегментный муксер открывает новый
        файл ровно тогда, когда закрыл прошлый. Мёртвый ffmpeg дописал всё, что успел.
        Докатка (номер меньше ``first``) не выкладывается никогда — она короче своего
        места в манифесте и под её именем может лежать честный сегмент прошлого прогона.
        """
        slots = sorted(s for s in map(segment_slot, _names(self.run)) if s >= 0)
        if not slots:
            return
        # Код 0 — ffmpeg дошёл до конца входа сам, дописан и последний кусок. Любой
        # другой исход (жив, убит, оборвался) последний кусок дописанным не делает.
        done = slots if self.proc.poll() == 0 else slots[:-1]
        for slot in done:
            path = self.run / segment_name(slot)
            # Ниже своего первого — докатка, выше последнего — обрезок за ``-to``
            # (:attr:`last`). И то и другое короче своего места в манифесте, и наружу
            # такое отдавать нельзя ни при каких обстоятельствах.
            if slot < self.first or 0 <= self.last < slot:
                path.unlink(missing_ok=True)
                continue
            # Кусок сейчас перекодируют — подождём его (:attr:`hold`). Дальше по списку не
            # идём: выложить следующий, оставив дыру, значит увести край за неё, и запрос
            # придержанного места выглядел бы для :meth:`Feed._steer` перемоткой назад.
            #
            # Спрашивающему отдаётся ВЕС уже готовой копии, и это не оптимизация, а
            # единственный честный замер: предсказание по карте зажато потолком
            # перекодирования и на «Тачках 3» промахнулось вчетверо (11.7 МБ против 51.4,
            # §6.2.6). Стоит он один ``stat`` на выложенный сегмент.
            size = 0
            with contextlib.suppress(OSError):
                size = path.stat().st_size
            if self.hold is not None and self.hold(slot, size):
                break
            # Перекодированный кусок этого же места лучше копии: то же разрешение и те же
            # метки, но битрейт, который приёмник тянет (§6.2). Копия при этом выбрасывается.
            better = self.spare / segment_name(slot) if self.spare is not None else None
            source = path
            if better is not None and better.exists():
                # Наружу идёт картинка перекода со звуком копии (:func:`merge_tracks`):
                # звук показа обязан остаться одним непрерывным потоком (§6.2.5).
                mixed = self.run / f"{MIXED_PREFIX}{slot}.ts"
                if merge_tracks(better, path, mixed):
                    source = mixed
                    better.unlink(missing_ok=True)
                else:
                    source = better
            moved = False
            with contextlib.suppress(OSError):
                os.replace(source, self.out / segment_name(slot))
                # Край двигает только состоявшееся переименование: «выложил» — это факт
                # этой строки, а не наличие файла в каталоге (:attr:`edge`).
                self.edge = max(self.edge, slot)
                moved = True
            if moved and source is not path:
                path.unlink(missing_ok=True)
            if moved and self.told is not None:
                with contextlib.suppress(Exception):
                    self.told(slot, source is not path)

    def cuts(self) -> list[tuple[int, float, float]]:
        """Что ffmpeg нарезал на самом деле: ``(сегмент, начало, конец)`` по его же списку.

        Нужно ровно для одного: сверить факт с манифестом (:meth:`drift`). Первую строку
        списка приходится пропускать — в ней ffmpeg пишет начало прогона нулём.
        """
        found: list[tuple[int, float, float]] = []
        try:
            text = (self.run / PACK_LIST).read_text("utf-8", "replace")
        except OSError:
            return found
        for line in text.splitlines():
            parts = line.strip().rstrip(",").split(",")
            if len(parts) < 3:
                continue
            slot = segment_slot(parts[0].rsplit("/", 1)[-1])
            with contextlib.suppress(ValueError):
                found.append((slot, float(parts[1]), float(parts[2])))
        return found

    def drift(self, grid: Grid) -> float:
        """Насколько нарезанное разошлось с обещанным в манифесте, секунды.

        Ноль (точнее, доли кадра) — манифест не врёт: ``EXTINF`` совпадает с фактом.
        Больше кадра — повод не верить нарезке и сказать об этом в журнал: значит, карта
        опорных кадров разошлась с потоком.
        """
        worst = 0.0
        for slot, began, _ in self.cuts()[1:]:
            if slot >= self.first:
                worst = max(worst, abs(began - grid.start(slot)))
        return worst

    def frontier(self) -> int:
        """Последний готовый сегмент в каталоге показа; ``first - 1`` — готового нет.

        ⚠️ Это **не** край прогона (:attr:`edge`): счёт идёт глобом каталога, где лежат и
        куски прошлых прогонов, поэтому после перемотки назад число врёт вверх. Решения
        об упаковке на нём больше не строятся (:meth:`Feed._steer`); осталось оно ровно
        под :meth:`Feed.front` — запас показа для сторожа приёмника, который доказан на
        живом ТВ и правится только с владельцем (§7.4 SPEC-v2, второй 🔴).
        """
        self.publish()
        slots = [s for s in map(segment_slot, _names(self.out)) if s >= self.first]
        return max(slots, default=self.first - 1)

    def halt(self) -> None:
        """Погасить упаковку, **не трогая уже упакованное**: приёмник на паузе, и копить
        сегменты в tmpfs незачем. Возобновление — новый прогон (:meth:`Feed.segment`).

        Раньше на этом месте стояла пауза сигналом (SIGSTOP). Она и оказалась классом
        проблемы §6 SPEC-v2: манифест замирает, а приёмник намертво виснет в BUFFERING —
        держит коннект и не запрашивает ничего. Поэтому процесс именно завершается.
        """
        self.halted = True
        self.stop(keep_files=True, reason="пауза на пульте")

    def poll(self) -> int | None:
        return self.proc.poll()

    def why(self) -> str:
        """Почему прогон кончился — наружу без трейсбеков (§6).

        Порядок ответов честный: сначала «мы сами» (:attr:`stopped`), потом слово ffmpeg,
        и только если он промолчал — код возврата. Молчание при коде 255 не загадка, а
        подпись нашего же SIGTERM (см. :attr:`stopped`), и выдавать её за аварию нельзя.
        """
        if self.stopped:
            return f"сняли сами: {self.stopped}"
        code = self.proc.poll()
        if code is not None and code < 0:
            return f"убит сигналом {-code}"  # сказать он не успел — не выдумываем за него
        lines: list[str] = []
        if self.log is not None:
            self.log.seek(0)
            text = self.log.read().decode("utf-8", "replace")
            lines = [ln for ln in text.splitlines() if ln.strip()]
        if lines:
            return lines[-1][:120]
        return "нет вывода" if code is None else f"молча, код {code}"

    def stop(self, keep_files: bool = False, reason: str = "") -> None:
        self.stopped = self.stopped or reason
        if self.proc.poll() is None:
            self.proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.proc.wait(timeout=5)
            if self.proc.poll() is None:
                self.proc.kill()
        self.publish()  # дописанное этим прогоном остаётся показу: оно уже верное
        shutil.rmtree(self.run, ignore_errors=True)
        if not keep_files:
            for junk in _paths(self.out):
                junk.unlink(missing_ok=True)


def merge_tracks(video: Path, audio: Path, dst: Path, timeout: float = _TIMEOUT) -> bool:
    """Собрать сегмент из картинки ``video`` и звука ``audio``; ``False`` — не вышло.

    Ради этого и написано (§6.2.5 SPEC-v2): **звук показа должен быть одним непрерывным
    потоком одного кодировщика**, а перекодированный кусок приносит свой.

    Кадровая сетка AAC отсчитывается от начала прогона ffmpeg: первый кадр встаёт на
    ``-ss`` этого прогона, дальше через 1024 сэмпла (21.33 мс). Упаковщик и кодировщик —
    разные прогоны с разными ``-ss``, поэтому их сетки сдвинуты друг относительно друга на
    произвольную долю кадра. Пока куски берутся из одного прогона, стык звука точен до
    микросекунды; на **первом** куске каждого захода перекода звук копии обрывается, а
    звук перекода начинается позже — замер на «Тачках 3» 07-08-2026: дыра **40.7 мс** на
    3973.678 при нуле на всех соседних стыках. Приёмник Q70D платит за эту дыру не сорока
    миллисекундами, а 2–5 секундами: он пересобирает синхронизацию.

    Поэтому наружу идёт картинка перекода со звуком копии — того самого прогона, что
    выложил соседние куски. Границы у них одни (сетка одна), метки абсолютные (``-copyts``),
    так что склейка — это переупаковка без единого перекодирования: 0.09–0.11 с на кусок
    12 МБ, замер на стенде.

    ⚠️ Не вышло — врать нельзя: возвращаем ``False``, и :meth:`Packer.publish` выложит
    перекод как есть. Это ровно сегодняшнее поведение, то есть худшее, что даёт отказ, —
    вернувшаяся заминка на одном куске, а не тишина и не тяжёлая копия.
    """
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-copyts",
        "-i", str(video), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
        "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", "-y", str(dst),
    ]  # fmt: skip
    try:
        done = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        dst.unlink(missing_ok=True)
        return False
    if done.returncode != 0 or not dst.exists() or dst.stat().st_size <= 0:
        dst.unlink(missing_ok=True)
        return False
    return True


def _names(out: Path) -> list[str]:
    return [path.name for path in out.glob("v*.ts")]


def _paths(out: Path) -> list[Path]:
    return list(out.glob("v*.ts"))


@dataclass(slots=True)
class Feed:
    """Упаковка по требованию: манифест обещает весь фильм, в tmpfs лежит окно (§2.1).

    Это ответ на железное ограничение: приёмнику нужен манифест на всю длительность,
    иначе у показа нет ни таймлайна, ни перемотки, — а целый фильм ни в RAM, ни на диск
    стенда не влезает. Развязка в том, что манифест и файлы живут порознь:

    * :meth:`Grid.manifest` перечисляет **все** сегменты фильма и не меняется никогда;
    * файлы под этими именами появляются только там, где приёмник смотрит прямо сейчас;
    * запрос сегмента, которого нет, — это и есть перемотка. Показ не отвечает 404
      (после него ресивер капризничает минутами), а перезапускает упаковку с нужного
      места и отдаёт кусок, как только он готов.

    Отсюда же берётся честная позиция: имя сегмента = его место в фильме, ``-copyts``
    держит исходные метки времени, и приёмник считает время от начала фильма, а не от
    начала куска. Никаких смещений показу пересчитывать не нужно.
    """

    source: str
    audio: int
    out: Path
    grid: Grid
    readrate: float = 1.0
    burst: float = 60.0
    #: Сколько секунд позади показа держим сегменты — глубина «бесплатной» перемотки назад.
    keep: float = 120.0
    #: Запрос дальше упакованного края больше чем на столько **сегментов** — это перемотка,
    #: а не обычный ход показа. Порог считается не от балды: после ``seek`` живой Q70D
    #: просит шесть сегментов разом (замерено), и ни один из них не должен считаться новой
    #: перемоткой. Раньше тут стояли секунды — с сеткой по опорным кадрам сегменты разной
    #: длины, и считать их надо штуками.
    ahead: int = 7
    #: Сколько секунд имеет смысл ЖДАТЬ упаковку вместо того, чтобы перезапустить её с
    #: нужного места (:meth:`Packer.eta`). Считать надо и штуками, и секундами: семь
    #: сегментов впереди края — это до семидесяти секунд фильма, а упаковка идёт в темпе
    #: реального времени, и ждать их пришлось бы столько же (§6.2.7).
    #:
    #: 15 с — вчетверо дороже перезапуска (пробный прогон, подъём ffmpeg и первый кусок
    #: стоят 3–4 с на живых смоках) и вчетверо дешевле замеренного ожидания на перемотке
    #: (57.8 с). Запас нужен с обеих сторон: после перезапуска приёмник просит шесть
    #: сегментов разом, и ни один не должен показаться новой перемоткой — но и не покажет,
    #: пока свежий прогон читает первые ``burst`` (60 с) на полной скорости.
    jump: float = 15.0
    #: Сколько держим запрос приёмника, пока упаковка догоняет. Это лучше 404: ресивер,
    #: поймавший 404, отказывается брать LOAD ещё пару минут (замерено 05-08-2026).
    #: ⚠️ Было 30 с — и этого мало: замерено 06-08-2026, когда TorrServer посреди показа
    #: выронил раздачу, упаковка встала, и через 30 с приёмник получил ровно тот 404,
    #: которого мы избегаем. Ждать почти бесплатно (это один поток раздачи), а зря
    #: ждать не придётся: безнадёжные случаи :meth:`_steer` отличает и говорит об этом.
    wait: float = 120.0
    #: Сколько раз упаковка успела оборваться сама. Пережить обрыв она обязана: TorrServer
    #: под просевшим роем закрывает вход, и ffmpeg честно умирает — а показу это уже не
    #: авария, потому что паковать заново он умеет с любого места. Но молча повторять до
    #: бесконечности нельзя: битый источник крутил бы этот круг вечно.
    limit: int = 3
    packer: Packer | None = None
    lock: Any = field(default_factory=threading.Lock)
    #: Когда последний раз перезапускали упаковку: защита от лавины на префетче.
    restarted: float = 0.0
    crashes: int = 0
    fatal: str = ""
    log: Any = None
    #: Кодировщик тяжёлых кусков (:class:`torrcast.recode.Recoder`) или ``None``, если
    #: динамический битрейт выключен либо тяжёлых кусков в фильме нет (§6.2).
    recoder: Any = None

    @property
    def duration(self) -> float:
        return self.grid.duration

    def manifest(self) -> bytes:
        return self.grid.manifest().encode("utf-8")

    def segment(self, slot: int) -> Path | None:
        """Файл сегмента ``slot``; ``None`` — его не будет (за концом фильма или не успели).

        Зовётся из потоков раздачи, поэтому решение о перезапуске упаковки принимается
        под замком: после перемотки приёмник просит несколько сегментов одновременно, и
        перезапустить упаковку должен ровно первый из них.
        """
        path = self.out / segment_name(slot)
        deadline = time.monotonic() + self.wait
        while True:
            if path.exists():
                return path
            with self.lock:
                hope = self._steer(slot)
            if path.exists():
                return path
            if not hope or time.monotonic() >= deadline:
                return None
            time.sleep(0.2)

    def _steer(self, slot: int) -> bool:
        """Что делать с упаковкой ради сегмента ``slot``; ``False`` — файла не будет.

        Разница между «подожди» и «не будет» — это разница между медленным ответом и 404.
        Держать приёмник в ожидании можно долго и почти безнаказанно, а вот 404 он
        запоминает: замерено 05-08-2026 — поймав его, ресивер не берёт LOAD ещё пару
        минут. Поэтому 404 отдаётся только там, где ждать нечего: конец входа или
        упаковка, которая сдалась насовсем.
        """
        if self.fatal:
            # Показ этой раздачи кончился (:meth:`stop`) или упаковка сдалась насовсем:
            # диагностировать тут больше нечего, а труп прогона — не новость. ⚠️ Проверка
            # стоит ПЕРВОЙ намеренно: на стыке серий сюда приходит приёмник, оставшийся
            # на живом keep-alive прошлой серии, и раньше он получал в журнал «упаковка
            # оборвалась» про наш же намеренно снятый ffmpeg (§7.4 SPEC-v2).
            return False
        packer = self.packer
        if packer is not None and not packer.halted:
            # Край берём честный — тот, что выложил ЭТОТ прогон (:attr:`Packer.edge`).
            # Глоб каталога (`frontier`) на этом месте и был багом §7.4: чужие куски
            # уводили край вперёд, запрос далеко назад попадал в «подожди, вот-вот
            # допакуется» — и висел все `wait` секунд, чтобы кончиться 404. Обратная
            # наивная починка («ждать только впереди глоба») давала 20 перезапусков за
            # 100 с. Работает только честный край: он растёт ровно на publish.
            packer.publish()
            if (self.out / segment_name(slot)).exists():
                # ⚠️ Кусок допаковался ровно этим `publish` — и это не редкость, а
                # обычный ход показа: приёмник идёт вплотную за упаковкой и просит
                # сегмент за мгновение до того, как тот закрылся. Без этой проверки он
                # оказывался «ниже края, а файла нет», то есть перемоткой назад: замер
                # на стенде 06-08-2026 — перезапуск на каждом четвёртом сегменте.
                return True
            code, edge = packer.poll(), packer.edge
            if code == 0 and slot > edge:
                return False  # упаковка честно дошла до конца входа — файла не будет
            if code is None and edge < slot <= edge + self.ahead:
                # ⚠️ «Вот-вот» — это про ВРЕМЯ, а не про номер сегмента, и разница стоила
                # 28 с чёрного экрана (§6.2.7). Упаковка идёт `readrate 1`, то есть в темпе
                # реального времени: перемотка вперёд внутри прогона попадает в эти семь
                # сегментов, но семь сегментов — это ещё и семьдесят секунд фильма, которые
                # ffmpeg будет читать семьдесят секунд. Замер на живом Q70D: перемотка
                # 3984 → 4100 (+116 с), «запрос v385.ts · ждал 57.8 с» — ровно эта планка.
                # Ждать имеет смысл только то, что упаковка достанет быстрее, чем стоит её
                # перезапуск с нужного места (:meth:`Packer.eta`).
                if packer.eta(self.grid.start(slot)) <= self.jump:
                    return True  # обычный ход показа: кусок вот-вот допакуется
                mark(
                    "перемотка внутри прогона",
                    слот=slot,
                    ждать=round(packer.eta(self.grid.start(slot)), 1),
                )
            # Всё остальное при живой упаковке — перемотка. Вперёд (дальше `ahead` за
            # краем) и назад (ниже края, а файла нет — значит выметен окном или паковал
            # его не этот прогон) лечатся одинаково: перепаковкой с этого места.
            if code not in (None, 0) and not self._survive(packer):
                return False
        if time.monotonic() - self.restarted < 2.0:
            return True  # соседний запрос уже перезапустил упаковку — не толкаемся
        self.restarted = time.monotonic()
        self.restart(slot)
        return True

    def _survive(self, packer: Packer) -> bool:
        """Упаковка оборвалась сама: пробуем ещё или сдаёмся честной ошибкой.

        ⚠️ Считаются ПРОГОНЫ, а не опросы. Пока держит защита «не толкаемся» (2 с),
        перезапуска не происходит, а потоки раздачи приходят сюда каждые 0.2 с — и один
        и тот же труп съедал все попытки меньше чем за секунду, не дав показу ни одного
        настоящего перезапуска. Ровно так выглядел бы обрыв входа сразу после старта:
        TorrServer выронил раздачу — ffmpeg умирает мгновенно, то есть внутри этих 2 с.
        """
        if packer.blamed:
            return True
        packer.blamed = True
        if packer.stopped:
            return True  # прогон сняли мы сами — это не обрыв, и попытку он не тратит
        self.crashes += 1
        why = packer.why()  # там же и код возврата, если ffmpeg смолчал
        if self.crashes > self.limit:
            self.fatal = why
            return False
        self._say(f"упаковка оборвалась ({why}) — начинаю заново, попытка {self.crashes}")
        return True

    def restart(self, slot: int) -> None:
        """Начать упаковку с сегмента ``slot``: перемотка, возврат с паузы или старт показа.

        Границы сегментов от места старта не зависят (:class:`Grid`), поэтому уже
        упакованное не выбрасывается: под именем ``vN`` и до, и после перезапуска лежит
        ровно одно и то же место фильма. Убирать приходится только то, что прошлый прогон
        не успел дописать, — а этого наружу и не попадало.
        """
        if self.packer is not None:
            self.packer.stop(keep_files=True)
        # ⚠️ Кодировщик узнаёт о новом месте показа ПЕРВЫМ делом, до пробного прогона
        # (0.5–1.7 с): голову прогона он обязан начать не позже упаковщика, иначе
        # придерживать её копию будет нечего и первый сегмент уйдёт тяжёлым (§6.2).
        if self.recoder is not None:
            self.recoder.opening(slot)
        at = pack_start(self.source, self.grid.start(slot))
        mark("пробный прогон", слот=slot, встали=round(at, 3))
        command = ffmpeg_pack_command(
            self.source,
            self.audio,
            str(self.out / PACK_DIR),
            self.grid,
            slot,
            at,
            self.readrate,
            self.burst,
        )
        self.restarted = time.monotonic()
        self.packer = Packer.start(
            command,
            self.out,
            self.out / PACK_DIR,
            slot,
            spare=None if self.recoder is None else self.recoder.spare,
            told=None if self.recoder is None else self.recoder.note,
            hold=None if self.recoder is None else self.recoder.holding,
            at=at,
            rate=self.readrate,
            burst=self.burst,
        )
        drop = self.grid.start(slot) - at
        self._say(
            f"упаковка с {self.grid.start(slot):.1f} с"
            + (f" (докатка {drop:.1f} с)" if drop > SPLIT_SLACK else "")
        )

    def prune(self, played: float) -> None:
        """Убрать из tmpfs то, чего показу уже не нужно, — и позади показа, и впереди.

        Позади окно ``keep`` секунд: глубже — уже перемотка, и она честно перепакует поток.

        Впереди убирается то, что осталось от **прошлого места показа**. После отката
        назад глубже окна упаковка идёт с нового места, а сегменты той минуты, откуда
        владелец ушёл, лежат в tmpfs и не выметаются ничем: окно смотрит только назад, а
        снова дойти до них показ может уже и не дойти. Десяток откатов подряд — и в
        памяти лежат места фильма, которых на экране не будет.

        Граница честная и не задевает ни запаса, ни префетча: остаётся всё, что этот
        прогон уже выложил или вот-вот выложит (``edge + ahead``), и всё, что рядом с
        позицией приёмника. Выше — куски, которых текущий прогон не делал и в ближайшее
        время не сделает. Упаковки нет вовсе — вперёд не трогаем ничего: без прогона край
        неизвестен, а гадать на этом месте дороже, чем подождать.
        """
        packer = self.packer
        keep_upto = -1
        if packer is not None:
            keep_upto = max(self.grid.slot_at(played), packer.edge) + self.ahead
        behind = self.grid.slot_at(played - self.keep) if played - self.keep > 0 else 0
        for path in _paths(self.out):
            slot = segment_slot(path.name)
            if slot < 0:
                continue
            if slot < behind or (keep_upto >= 0 and slot > keep_upto):
                path.unlink(missing_ok=True)

    def front(self, played: float = 0.0) -> float:
        """Докуда показ обеспечен **подряд** от позиции ``played``, секунды от начала фильма.

        Разница между этим числом и позицией приёмника — весь запас показа. Он и есть
        предмет §6 SPEC-v2: пока запас положителен, приёмнику всегда есть что взять, а
        как только он сходит в ноль — приёмник встаёт в BUFFERING. На этом числе стоит
        сторож приёмника: неподвижный BUFFERING при живом запасе — зависание и лечится
        нуджем, при пустом — законное ожидание нас и лечится упаковкой.

        ⚠️ Раньше здесь стоял глоб каталога (``Packer.frontier``), и после перемотки назад
        он врал в разы: в каталоге показа лежат честные куски прошлых прогонов (сетка
        детерминирована, §6.0), и «докуда упаковано» считалось по ним. Замер на живом
        Q70D 06-08-2026: откат с 40-й минуты на 10-ю — «показ 600 · упаковано 2010 ·
        впереди 1410 с», при том что перед приёмником не было ни одного куска. Запас,
        посчитанный за тысячу секунд от места, где показа нет, — это разрешение сторожу
        дёргать приёмник ровно тогда, когда дёргать нельзя.

        Правда считается от приёмника и только по фактам: кусок под позицией и цепочка
        за ним. Разрыв цепочки — конец запаса, что бы ни лежало дальше: перепрыгнуть
        дырку приёмник всё равно не сможет. Куска под позицией нет вовсе — запаса ноль.
        """
        slot = self.grid.slot_at(played)
        if not (self.out / segment_name(slot)).exists():
            return played
        while slot + 1 < self.grid.count and (self.out / segment_name(slot + 1)).exists():
            slot += 1
        return self.grid.end(slot)

    def drift(self) -> float:
        """Насколько нарезанное разошлось с манифестом, секунды (:meth:`Packer.drift`)."""
        return 0.0 if self.packer is None else self.packer.drift(self.grid)

    def weight(self) -> int:
        """Сколько байт сегментов лежит в tmpfs прямо сейчас (§6: рост без предела —
        недопустим, а это единственный способ увидеть пик своими глазами)."""
        total = 0
        for path in _paths(self.out):
            with contextlib.suppress(OSError):  # вычистило окном прямо сейчас
                total += path.stat().st_size
        return total

    def trouble(self) -> str:
        """Почему показ дальше не идёт, если не идёт; пусто — всё в порядке.

        Мёртвый ffmpeg сам по себе поводом остановить показ не является: код 0 — это
        конец входа (остаток фильма уже в tmpfs), а обрыв лечится следующей упаковкой.
        Ошибкой это становится, только когда обрывы пошли подряд (:attr:`limit`).
        """
        return self.fatal

    def halted(self) -> bool:
        return self.packer is not None and self.packer.halted

    def halt(self) -> None:
        if self.packer is not None:
            self.packer.halt()

    def stop(self) -> None:
        """Показ окончен: упаковка гаснет, каталог показа пустеет.

        Флажок «картинка на экране» снимается ровно здесь и больше нигде: пока показ идёт,
        он и есть доказательство картинки для CLI (§4 SPEC-v2), поэтому перезапуски
        упаковки (:meth:`restart`, перемотка) его не трогают. А после остановки это уже
        не доказательство, а пустой файл, который переживал `cast stop` в tmpfs.
        """
        # Закрыто насовсем: поток раздачи, спящий в segment() до двух минут, не должен
        # проснуться и поднять новый ffmpeg в каталог, который уже отдан следующей серии.
        self.fatal = self.fatal or "показ окончен"
        if self.recoder is not None:
            self.recoder.stop()
        if self.packer is not None:
            self.packer.stop()
        for junk in _paths(self.out):
            junk.unlink(missing_ok=True)
        shutil.rmtree(self.out / PACK_DIR, ignore_errors=True)
        shutil.rmtree(self.out / RECODE_DIR, ignore_errors=True)
        forget_playing(self.out)

    def _say(self, text: str) -> None:
        if self.log is not None:
            self.log(text)


def _scope() -> list[str]:
    """Юнит системный, когда мы root (так на стенде из ``install.sh``), иначе
    пользовательский (так на dev). Постоянных юнитов у нас нет ни там, ни там — только
    transient на время показа (§3).
    """
    return [] if os.geteuid() == 0 else ["--user"]


def _systemd(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [tool, *_scope(), *args], capture_output=True, text=True, check=False, timeout=60
    )


def start_play_unit(key: str, unit: str = _UNIT_NAME) -> None:
    """Запустить показ в transient-юните: ``cast`` завершился — показ продолжается,
    логи бесплатно в journald (§3). Переменные окружения проброшены, иначе юнит возьмёт
    прод-пути конфига и состояния вместо dev-овских.
    """
    stop_play_unit(unit)
    env = [f"--setenv={n}={os.environ[n]}" for n in _PASS_ENV if n in os.environ]
    done = _systemd(
        "systemd-run", f"--unit={unit}", "--collect", "--quiet",
        f"--description={_UNIT_TAG}{key}", *env,
        sys.executable, "-m", "torrcast.cli", "--play-key", key,
    )  # fmt: skip
    if done.returncode != 0:
        raise InfraError(f"не запустился юнит {unit}: {done.stderr.strip()[:120] or 'systemd-run'}")


def stop_play_unit(unit: str = _UNIT_NAME) -> None:
    """Погасить transient-юнит и дождаться его смерти: по SIGTERM сторож дописывает
    позицию в state. Отсутствие юнита ошибкой не считается.
    """
    _systemd("systemctl", "stop", unit)


def unit_active(unit: str = _UNIT_NAME) -> bool:
    """Идёт ли показ прямо сейчас."""
    return _systemd("systemctl", "is-active", unit).stdout.strip() == "active"


def unit_key(unit: str = _UNIT_NAME) -> str:
    """Ключ состояния играющего показа — из ``--description`` юнита. Свежайшая запись в
    state для этого не годится: рядом мог писать другой ход, и ``status`` соврал бы.
    """
    found = _systemd("systemctl", "show", unit, "-p", "Description", "--value").stdout.strip()
    return found[len(_UNIT_TAG) :].strip() if found.startswith(_UNIT_TAG) else ""


def unit_why(unit: str = _UNIT_NAME) -> str:
    """Последняя внятная строка юнита из journald — наружу без трейсбеков (§6)."""
    out = _systemd("journalctl", "-u", unit, "-n", "10", "--no-pager", "-o", "cat").stdout
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return lines[-1][:160] if lines else "в журнале пусто"


def _opt_str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


#: Отдаём ровно манифест и сегменты сетки, и ничего больше: каталог наружу не открыт.
_ASSET_RE: Final = re.compile(r"^(?:v\d+\.ts|index\.m3u8)$")
_TYPES: Final = {".m3u8": "application/vnd.apple.mpegurl", ".ts": "video/mp2t"}
_RANGE_RE: Final = re.compile(r"bytes=(\d*)-(\d*)")
#: ``TORRCAST_TRACE=1`` — раздача пишет в журнал каждый запрос приёмника (:meth:`_Handler._trace`).
TRACE: Final = bool(os.environ.get("TORRCAST_TRACE"))


class _Handler(http.server.BaseHTTPRequestHandler):
    """Манифест и сегменты: CORS на всех ответах, Range на сегментах, ноль лишних путей.

    Range обязателен: ресивер Q70D переспрашивает куски диапазонами (грабли kinocast),
    а без ``Access-Control-Allow-Origin: *`` Chromecast молча не играет (§3, §9).

    Манифест берётся не с диска, а у :class:`Feed`: он описывает весь фильм, а не то,
    что успело упаковаться (§2.1 SPEC-v2). Запрос сегмента тоже уходит в ``Feed`` —
    именно там запрос неупакованного места превращается в перемотку.
    """

    protocol_version = "HTTP/1.1"
    server_version = "torrcast"
    root: Path = Path()
    feed: ClassVar[Feed | None] = None

    def do_GET(self) -> None:
        self._serve(body=True)

    def do_HEAD(self) -> None:
        self._serve(body=False)

    def do_OPTIONS(self) -> None:
        self._head(204, 0, "text/plain")

    def _serve(self, body: bool) -> None:
        began = time.monotonic()
        name = self.path.split("?")[0].lstrip("/")
        if not _ASSET_RE.fullmatch(name):
            self._head(404, 0, "text/plain")
            return
        data = self._read(name)
        if data is None:
            self._head(404, 0, "text/plain")
            self._trace(name, began, "404")
            return
        self._trace(name, began, f"{len(data) / 1e6:.1f} МБ")
        suffix = ".m3u8" if name.endswith(".m3u8") else ".ts"
        ctype, total = _TYPES[suffix], len(data)
        span = self._range(total)
        if span is None:
            self._head(200, total, ctype)
        elif not span:
            self._head(416, 0, ctype, (("Content-Range", f"bytes */{total}"),))
            return
        else:
            first, last = span
            data = data[first : last + 1]
            self._head(206, len(data), ctype, (("Content-Range", f"bytes {first}-{last}/{total}"),))
        if body:
            sent = time.monotonic()
            self.wfile.write(data)
            self._sent(name, len(data), time.monotonic() - sent)

    def _read(self, name: str) -> bytes | None:
        """Тело ответа: манифест на весь фильм или сегмент, дождавшись упаковки."""
        if name.endswith(".m3u8"):
            return self.feed.manifest() if self.feed is not None else None
        path = self.root / name
        if self.feed is not None:
            found = self.feed.segment(segment_slot(name))
            if found is None:
                return None
            path = found
        try:
            return path.read_bytes()
        except OSError:  # вычистило окном ровно между проверкой и чтением
            return None

    def _range(self, size: int) -> tuple[int, int] | tuple[()] | None:
        found = _RANGE_RE.fullmatch(self.headers.get("Range", "").strip())
        if not found:
            return None
        head, tail = found.group(1), found.group(2)
        if not head:
            first, last = max(0, size - int(tail or 0)), size - 1
        else:
            first, last = int(head), min(int(tail) if tail else size - 1, size - 1)
        return (first, last) if first <= last < size else ()

    def _head(self, code: int, length: int, ctype: str, extra: tuple[Any, ...] = ()) -> None:
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        # Кэшировать нельзя ничего: манифест дописывается на ходу, а после перепаковки
        # (перемотка назад глубже окна, §6 SPEC-v2) под теми же именами сегментов лежит
        # уже другое место фильма — кэш приёмника показал бы старое.
        self.send_header("Cache-Control", "no-store")
        for key, value in extra:
            self.send_header(key, value)
        self.end_headers()

    def _trace(self, name: str, began: float, got: str) -> None:
        """Что попросил приёмник, сколько ждал ответа и что получил (``TORRCAST_TRACE=1``).

        Без этого §6 SPEC-v2 не измерить: подвис приёмника снаружи выглядит одинаково и
        когда он ждёт нас, и когда он перестал спрашивать вовсе, — а лечится это по-разному.
        """
        if not TRACE:
            return
        span = self.headers.get("Range", "")
        print(
            f"запрос {name}{' ' + span if span else ''} · ждал {time.monotonic() - began:.1f} с"
            f" · {got}",
            flush=True,
        )

    def _sent(self, name: str, size: int, seconds: float) -> None:
        """Сколько времени кусок **уезжал в телевизор** (``TORRCAST_TRACE=1``).

        Не то же самое, что :meth:`_trace`: тот меряет, сколько мы искали кусок, а этот —
        сколько заняла отдача по сети. Без этого числа не отличить «показ споткнулся о
        нарезку» от «канал до ТВ не тянет этот кусок»: с диска всё отдаётся мгновенно, а
        уезжает ровно столько, сколько позволяет линк.
        """
        if not TRACE or seconds <= 0:
            return
        print(
            f"отдал {name} · {size / 1e6:.1f} МБ за {seconds:.1f} с"
            f" · {size * 8 / seconds / 1e6:.1f} Мбит/с",
            flush=True,
        )

    def log_message(self, fmt: str, *args: Any) -> None:
        pass


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    #: Контекст TLS или ``None`` — тогда раздача идёт голым http (дефолт, §5 SPEC-v2).
    ctx: ssl.SSLContext | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        #: Живые соединения приёмника. Нужны ровно затем, чтобы их можно было закрыть
        #: (:meth:`drop_live`): раздача HTTP/1.1, приёмник держит один keep-alive на весь
        #: показ, а ``server_close`` закрывает только слушающий сокет.
        self._live: set[Any] = set()
        super().__init__(*args, **kwargs)

    def get_request(self) -> tuple[Any, Any]:
        # Слушающий сокет остаётся обычным TCP, рукопожатие уходит в рабочий поток:
        # иначе один полуоткрытый коннект вешает весь accept (грабли kinocast).
        sock, addr = super().get_request()
        sock.settimeout(60)
        if self.ctx is not None:
            sock = self.ctx.wrap_socket(sock, server_side=True, do_handshake_on_connect=False)
        self._live.add(sock)
        return sock, addr

    def shutdown_request(self, request: Any) -> None:
        self._live.discard(request)
        super().shutdown_request(request)

    def drop_live(self) -> None:
        """Закрыть соединения приёмника — раздача кончилась вместе с этим показом.

        ⚠️ Без этого «раздача остановлена» не значит «раздача молчит». Потоки-обработчики
        демонические и ``server_close`` их не ждёт (``block_on_close`` при
        ``daemon_threads``), а приёмник ходит по HTTP/1.1 и держит **одно** соединение на
        весь показ. На стыке серий оно переживало и упаковку, и раздачу прошлой серии: LOAD
        следующей уходил в тот же сокет, и отвечал на него уже остановленный
        :class:`Feed` — манифест прошлой серии и мгновенный 404 на ``v0.ts``. Дальше
        приёмник отвечал ``IDLE/ERROR``, и владелец видел 15 с чёрного экрана (§7.4
        SPEC-v2, замер живого Q70D 06-08-2026).
        """
        for sock in list(self._live):
            self._live.discard(sock)
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)

    def handle_error(self, request: Any, client_address: Any) -> None:
        pass  # битое рукопожатие или оборванный приёмник — не наша авария


class HlsServer:
    """Раздача HLS с самого стенда (§3): в облако поток не уходит.

    Дефолт — голый http (§5 SPEC-v2): ТВ ходит по IP, ни серта, ни имени, ни DNS в пути
    показа нет. ``tls=True`` включает прежнюю https-раздачу — код жив и работает, но
    требует серта, которому доверяет ТВ (Chromecast self-signed молча не принимает, §9).
    """

    def __init__(
        self,
        root: Path,
        cert: str = "",
        key: str = "",
        host: str = "0.0.0.0",
        port: int = 8080,
        tls: bool = False,
        feed: Feed | None = None,
    ):
        self.root, self.cert, self.key, self.host, self.port = root, cert, key, host, port
        self.tls = tls
        self.feed = feed
        self._server: _Server | None = None

    def start(self) -> None:
        ctx = None
        if self.tls:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            try:
                ctx.load_cert_chain(self.cert, self.key)
            except (OSError, ssl.SSLError) as exc:
                raise InfraError(f"не читается серт {self.cert}: {why(exc)}") from exc
        handler = type("_Bound", (_Handler,), {"root": self.root, "feed": self.feed})
        try:
            server = _Server((self.host, self.port), handler)
        except OSError as exc:
            raise InfraError(f"порт {self.port} занят или недоступен: {why(exc)}") from exc
        server.ctx = ctx
        self._server = server
        threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True
        ).start()

    def stop(self) -> None:
        """Погасить раздачу целиком: и слушающий сокет, и живые соединения приёмника.

        Второе так же обязательно, как первое (:meth:`_Server.drop_live`): показ, который
        остановлен, обязан замолчать, а не досказывать прошлую серию в keep-alive.
        """
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server.drop_live()
            self._server = None


def our_address(tv: str) -> str:
    """Наш адрес **с той стороны, с которой нас видит ТВ**, или пусто, если маршрута нет.

    У стенда две ноги: ``192.168.1.62`` в домашней сети и ``192.168.100.62`` в сегменте
    телевизора. Ядро выбирает исходящий адрес по маршруту, поэтому спрашиваем его же:
    сокет никуда не подключается по-настоящему (UDP, ни одного пакета), но имя ему
    присваивается ровно то, которое ТВ увидит источником. Так поток идёт в одном L2, а
    не лишним хопом через SNAT маршрутизатора.
    """
    if not tv:
        return ""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((tv, 8009))
        return str(sock.getsockname()[0])
    except OSError:
        return ""
    finally:
        sock.close()


def hls_base(config: Config) -> str:
    """База URL, под которой ТВ забирает манифест и сегменты (§5 SPEC-v2).

    Имени здесь нет и быть не должно: адрес собирается из транспорта, нашей ноги со
    стороны ТВ и порта — DNS в пути показа не участвует. ``hls_base_url`` в конфиге,
    если он задан, перебивает всё: это запасной выход на случай, когда прямой путь
    почему-то не работает.
    """
    if config.hls_base_url:
        return config.hls_base_url.rstrip("/")
    host = our_address(config.tv or "")
    if not host:
        raise InfraError(f"не вижу маршрута до ТВ {config.tv or '(адрес не задан)'}")
    return f"{config.transport}://{host}:{config.hls_port}"
