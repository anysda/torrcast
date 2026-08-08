"""CLI — единственный наш процесс.

Контракт: ``cast <запрос> [sNeM] [--new] [--dry]``, отладочные ручки ``--release N`` /
``--file N`` / ``--voice N`` / ``cast releases <запрос>`` / ``cast voices <запрос>``,
а также ``cast stop``, ``cast status``, ``cast doctor``, ``cast --tv <ip>``. Коды
выхода: ``0`` ок · ``1`` не нашли · ``2`` инфра-ошибка; наружу — короткие русские
строки без трейсбеков.

Счастливый путь — **один вопрос** и ни одного упоминания файлов: «какой фильм
франшизы?», и тот пропускается, когда картина одна. Релиз и озвучка выбираются сами,
о выборе говорится вслух, а таблица релизов, список файлов и меню озвучек уезжают в
отладочные ручки. Второй вопрос бывает ровно один — «Продолжить?» у начатой картины:
он про намерение, а не про технику.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import shutil
import signal
import sys
import textwrap
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

from torrcast import (
    InfraError,
    NotFoundError,
    TorrcastError,
    __version__,
    console,  # через модуль: терминал спрашиваем там же, где и сами вопросы
    trace,
    why,
)
from torrcast.cast import ChromecastReceiver, Receiver, make_receiver
from torrcast.console import Progress, ask, ask_line, terminal
from torrcast.facts import Fact, Facts, Origin, origin, shorten
from torrcast.parse import (
    VIDEO_EXT,
    Episode,
    EpisodeFile,
    Picture,
    Release,
    franchise_key,
    map_episodes,
    menu_order,
    other_words,
    outside_numbering,
    slugify,
    split_episode,
    split_franchise_index,
    transliterate,
)
from torrcast.recode import FULL_FLOOR, FULL_GAIN, FULL_PRESET, Encode, Recoder
from torrcast.search import Prowlarr, RawResult, merge, to_releases
from torrcast.state import Config, Entry, State, load_config, save_config
from torrcast.stream import (
    KEYS_WAIT,
    PILOT_TIMEOUT,
    RECODE_CODECS,
    AudioTrack,
    Feed,
    Grid,
    HlsServer,
    Media,
    TorrFile,
    TorrServer,
    bitrate_mbit,
    forget_playing,
    hls_base,
    mark_playing,
    pick_video_file,
    playing_flag,
    probe,
    recode_note,
    start_play_unit,
    stop_play_unit,
    swarm_pulse,
    unit_active,
    unit_key,
    unit_why,
    warm_file,
)
from torrcast.timing import mark
from torrcast.warm import Vault, Warmer, warm_key, warm_root

__all__ = [
    "Args",
    "bitrate_of",
    "gate_open",
    "honest_shot",
    "is_dated",
    "is_dead",
    "is_full_hd",
    "liveliest",
    "liveliness",
    "main",
    "misses_episode",
    "parse_args",
    "pick_voice",
    "promises_more",
    "quality_text",
    "rank_releases",
    "render_table",
    "sound_note",
    "sound_step",
    "spoken",
    "understated",
    "voices_table",
    "warm_order",
]

EXIT_OK, EXIT_NOT_FOUND, EXIT_INFRA = 0, 1, 2
#: Сколько строк таблицы релизов показываем: ниже начинаются раздачи без сидов.
TABLE_LIMIT = 12
#: Сколько ПРИГОВОРОВ подряд терпим, прежде чем сдаться: подмены не молчат. Приговор -
#: это когда ffprobe раздачу прочитал и она не годится (av1, vc1, тяжёлая). Осечка роя
#: приговором не считается и попытку не жжёт (:meth:`_Bench.resolve`).
MAX_TRIES = 3
#: ``--voice`` без номера: показать меню озвучек. Ноль тут свободен - дорожки для
#: человека нумеруются с единицы.
VOICE_MENU = 0
#: Сколько картин франшизы греем под меню: топ-2-3 релиза уходят в TorrServer фоном,
#: пока человек отвечает на вопросы.
PREWARM = 3
#: Бюджет одной раздачи на метаданные по DHT, секунды. Не уложилась - не «зависли
#: насмерть», а честная строка и следующий релиз.
META_BUDGET = 20.0
#: Бюджет на чтение дорожек (ffprobe) той же раздачи, секунды.
PROBE_BUDGET = 40.0
#: Сколько ffprobe ждёт первых байт потока, прежде чем счесть рой мёртвым, секунды.
#: Раздача с мёртвым роем метаданные отдаёт (они уже в TorrServer), а содержимого не
#: отдаёт вовсе - и раньше на ней сгорал весь :data:`PROBE_BUDGET` (сорок секунд на одном
#: молчащем релизе, когда рядом в очереди стояли живые). Отсрочка отделяет такой рой от
#: честно долгого заголовка («Моана 2» едет 17 с): ни байта за неё - пиров нет, обрываем
#: и берём запасного, он уже греется параллельно (:func:`torrcast.stream.swarm_pulse`).
SWARM_GRACE = 12.0
#: **Бюджет всей фазы отбора, секунды**: столько CLI перебирает очередь, прежде чем
#: сдаться. Число не новое и не «с запасом»: это ровно прежний потолок фазы - три
#: попытки, каждая по полному бюджету раздачи (:data:`META_BUDGET` + :data:`PROBE_BUDGET`).
#: Потолок остался тем же, изменилось только, на что он тратится: раньше в него
#: укладывались строго три раздачи, теперь - сколько успеет, пока осечки идут молчанием
#: роя. Осечки эти дешёвые: запасной греется параллельно с текущим, поэтому мёртвая
#: раздача стоит не двадцати секунд, а разницы между двумя ожиданиями DHT.
PICK_BUDGET = MAX_TRIES * (META_BUDGET + PROBE_BUDGET)
#: Сколько ждём ответа от честного запасного, если верх оказался хуже, чем обещал. Запасной
#: к этой секунде уже греется (:meth:`_Bench.resolve` поднимает следующего сразу), так что
#: платим не за прогрев, а за разницу между двумя ffprobe. Не уложился - играем то, что
#: есть, и говорим об этом вслух: лишние секунды старта хуже, чем 574p.
HONEST_BUDGET = 12.0
#: Ниже этой высоты кадра HD уже не назовёшь. Имя раздачи о разрешении молчит чаще, чем
#: врёт (у «Моаны 2» - в 5 именах из 11), поэтому «имя молчало, а внутри SD» - такой же
#: повод посмотреть на соседа, как и прямое враньё в имени.
HD_HEIGHT = 720
#: Ступень, ради которой затеян отбор: честный 1080p. Имя, называющее её (или выше),
#: поднимается над названным 720p - но только если раздача жива (:func:`is_full_hd`).
FULL_HEIGHT = 1080
#: Насколько живым обязан быть названный 1080p, чтобы обойти 720p: доля от сидов самой
#: обсиженной раздачи картины. Не абсолютное число, потому что живость у картин разная:
#: у новинки лидер набирает сотни сидов, у кино 1994 года - четыре десятка, и «20 сидов»
#: означало бы в этих двух пулах совершенно разное. Замер по живой выдаче: у «Мастера и
#: Маргариты» 1080p держит 0.40 от лидера (59 против 146) и обязан выиграть, у «Зелёной
#: мили» - 0.10 (4 против 38), у «Форреста Гампа» - 0.05 (2 против 41), и эти обязаны
#: проиграть: 15 ГБ на двух сидах - это не 1080p, а подгрузы.
FULL_HD_LIVENESS = 0.25
#: Насколько живым обязан быть именной кандидат, чтобы ворота отбора остались закрытыми:
#: доля от сидов самой обсиженной раздачи картины. Доля, а не абсолютное число, ровно по
#: той же причине, что и у :data:`FULL_HD_LIVENESS`.
#:
#: Замер по живой выдаче «наруто»: у картины «Наруто» (2002) именных кандидатов два - на
#: 3 и на 1 сид, - а полный сериал «[E220 of 220]» с 91 сидом в кандидаты не проходил
#: вовсе. 3/91 = 0.03: живым такой кандидат не назовёшь, и выбор между ним и ничем - это
#: выбор между подгрузами и подгрузами. У фильмов с богатой выдачей доля лидера-кандидата
#: заметно выше порога, и ворота там не открываются никогда.
GATE_LIVENESS = 0.25
#: Насколько живым обязан быть релиз с обещанной русской дорожкой, чтобы обойти по звуку
#: более обсиженного соседа (:func:`sound_step`). Порог ниже, чем у HD (0.10 против 0.25),
#: и это не небрежность: «1080p вместо 720p» - оттенок, а «по-русски вместо по-японски» -
#: разница между «посмотрел» и «не посмотрел», и платить за неё сидами можно дороже.
#: Замер по живой выдаче: у «Врат Штейна» русский BDRip 1080p держит 86 сидов против 397
#: у самого живого «[Anime Time]» - 0.22, и обязан выиграть; у «Наруто: Ураганные
#: хроники» русская раздача имеет НОЛЬ сидов против трёх - 0.0, и обязана проиграть,
#: потому что мёртвый рой это не показ ни на каком языке.
SOUND_LIVENESS = 0.10
#: Насколько подтверждённая высота вправе отставать от заявленной. 0.9 - это про обрезку
#: чёрных полей: у 1080p-широкоформатника реальная высота 800-816, и релиз честен. А
#: 574 против 1080 - это уже другая ступень лестницы, а не кадрирование.
HONEST_RATIO = 0.9
#: Потолок ожидания метаданных раздачи **в юните**, секунды. Здесь это не «бюджет фазы
#: под меню» (:data:`META_BUDGET`), а последний рубеж: магнит юниту уже дали, и если
#: метаданные не приехали, показывать нечего.
WORKER_META = 60.0
#: Потолок ffprobe длительности в юните: своей длительности следующая серия не знает, и
#: читается она из потока (:func:`_duration`).
WORKER_DUR = 90.0
#: Прочее на пути юнита до картинки, у чего своего потолка нет: запуск transient-юнита,
#: чтение состояния, подъём раздачи. Секунды, но считать их нулём - врать себе.
START_SLACK = 10.0
#: **Бюджет старта показа: столько CLI ждёт картинку на экране** (:func:`_await_playing`).
#:
#: Число не выбирается на глаз и не «берётся с запасом»: это сумма потолков всех фаз,
#: которые юнит проходит от запуска до первого ``PLAYING``, - метаданные раздачи, ffprobe
#: длительности, ожидание чужой карты опорных кадров, пробный прогон упаковки и терпение
#: приёмника к молчаливому ``IDLE``. Пока CLI ждал меньше суммы (120 с против 60 + 90 +
#: 60), он гасил `stop_play_unit`'ом показ, который вот-вот начался бы.
#:
#: Ждать так долго не страшно и не молчаливо: :class:`~torrcast.console.Progress` всё это
#: время показывает живую фазу, а любая честная неудача убивает юнит раньше - CLI видит
#: это по :func:`unit_active` и печатает причину из журнала, не досиживая до конца.
START_BUDGET = (
    WORKER_META
    + WORKER_DUR
    + KEYS_WAIT
    + PILOT_TIMEOUT
    + START_SLACK
    + ChromecastReceiver.START_TIMEOUT
)
#: Как часто сторож кладёт позицию в state, секунды.
WATCH_SECONDS = 10.0
#: Доля фильма, с которой прогрев считается полным в статусе. Не единица: хвост сетки
#: короче шага, и последний кусок доезжает позже всех - а «интернет не нужен» верно уже
#: тогда, когда впереди лежит всё, что зритель успеет посмотреть.
WARMED_RATIO = 0.99
#: Как часто показ пишет в журнал, что видит приёмник: позиция и общее время -
#: единственное доказательство того, что на экране есть таймлайн.
SAY_SECONDS = 30.0
#: ``TORRCAST_TRACE=1`` - писать в журнал запас показа на каждом опросе (раз в 2 с):
#: позиция приёмника, край упаковки, разница между ними и вес tmpfs. Инструмент про
#: устойчивость: её провал видно только в динамике запаса, а раз в 30 с он теряется.
TRACE_ENV = "TORRCAST_TRACE"
#: ``TORRCAST_CTL=<файл>`` - диагностический пульт показа: строка в файле («``seek 1200``»,
#: «``pause``», «``play``») исполняется владеющим сендером на ближайшем опросе, файл
#: съедается. Нужен ровно затем, что кнопку на пульте может нажать только человек, а
#: вторым pychromecast команду не подать вовсе: приёмник считает второе соединение тем же
#: сендером и отвечает пустым MEDIA_STATUS (докстринг :class:`ChromecastReceiver`).
#: Приёмнику это приходит той же MEDIA-командой, что и с пульта, поэтому проверка честная.
#: На счастливом пути не участвует: переменной нет - кода нет.
CTL_ENV = "TORRCAST_CTL"
#: Сколько терпим паузу на пульте, прежде чем погасить упаковку: дальше
#: сегменты копились бы в tmpfs впустую - приёмник их не забирает.
PAUSE_SECONDS = 60.0
#: Пауза длиннее этого - показ считается оконченным: юнит гаснет и не держит раздачу.
PAUSE_LIMIT = 3600.0
#: Битрейт, ниже которого раздача без единого маркера качества в имени - это SD-рип
#: (MPEG-4 в .avi), а не скромный 1080p. Порог выбран по замеру, а не на глаз: из 264
#: раздач живой выдачи («моана», «тачки», «матрица», «интерстеллар», «аватар») удалось
#: достать .torrent и заглянуть внутрь у 36. Все восемь .avi в этой выборке не называют
#: ни разрешения, ни кодека, и у пяти полнометражных потолок вышел 3.5 Мбит/с; ближайший
#: снизу подтверждённый .mkv с такой же безымянной шапкой - 5.4 Мбит/с. Порог поставлен
#: посередине этого зазора.
SD_BITRATE = 4.0
#: Признаки образа диска в имени раздачи - внутри VOB/BDMV, а не один файл.
_DISC_RE = re.compile(
    r"\b(?:video_?ts|bdmv|dvd[- ]?video|dvd[59]|iso|blu-?ray\s*(?:disc|cee)|avc\+?\s*iso)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class Args:
    query: list[str]
    tv: str | None = None
    release: int | None = None
    file: int | None = None
    #: ``--voice N`` - играть дорожку N; ``--voice`` без номера (:data:`VOICE_MENU`) -
    #: показать меню озвучек и спросить. На счастливом пути обоих нет: озвучка
    #: выбирается сама.
    voice: int | None = None
    new: bool = False
    dry: bool = False
    #: ``cast log --since 2d|12h|30m|ГГГГ-ММ-ДД`` - с какого момента показывать след.
    since: str | None = None
    #: Внутреннее: показ внутри transient-юнита, руками не зовётся.
    play_key: str | None = None

    @property
    def command(self) -> str:
        """``stop`` / ``status`` / ``doctor`` / ``releases`` / ``voices`` / ``play`` /
        ``configure`` / ``worker``.
        """
        if self.play_key:
            return "worker"
        words = {"stop", "status", "doctor", "releases", "voices", "log"}
        if self.query and self.query[0] in words:
            return self.query[0]
        if not self.query:
            return "configure" if self.tv else "status"
        return "play"

    @property
    def episode(self) -> Episode | None:
        """Явно указанная серия: ``cast киберпанк s2e5``, ``2x5``, «2 сезон 5 серия»."""
        return split_episode(" ".join(self.query))[1]

    @property
    def title_query(self) -> str:
        """Запрос без указания серии: искать надо «киберпанк», а не «киберпанк 2x5»."""
        return split_episode(" ".join(self.query))[0]

    @property
    def pinned(self) -> bool:
        """Релиз или файл названы руками — отладочный путь, подмен в нём не бывает."""
        return self.release is not None or self.file is not None


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """Разобрать argv по контракту CLI."""
    about = "torrcast - найти релиз и кастить его на ТВ без скачивания"
    parser = argparse.ArgumentParser(prog="cast", description=about, allow_abbrev=False)
    parser.add_argument("query", nargs="*", help="название, либо stop / status")
    parser.add_argument("--tv", metavar="IP", help="разовая настройка адреса ТВ (или mock)")
    parser.add_argument("--release", type=int, metavar="N", help="отладка: взять релиз N")
    parser.add_argument("--file", type=int, metavar="N", help="отладка: взять файл N раздачи")
    parser.add_argument(
        "--voice",
        type=int,
        nargs="?",
        const=VOICE_MENU,
        metavar="N",
        help="озвучка: N - взять дорожку N и запомнить, без номера - меню",
    )
    # Прежнее имя того же флага: ломать чужие пальцы и историю оболочки незачем.
    parser.add_argument(
        "--audio", type=int, nargs="?", const=VOICE_MENU, dest="voice", help=argparse.SUPPRESS
    )
    parser.add_argument("--new", action="store_true", help="забыть прогресс и выбрать заново")
    parser.add_argument("--dry", action="store_true", help="весь резолв без каста")
    parser.add_argument(
        "--since", metavar="СРОК", help="cast log: с какого момента (2d / 12h / 30m / ГГГГ-ММ-ДД)"
    )
    parser.add_argument("--play-key", metavar="KEY", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="version", version=f"torrcast {__version__}")
    return Args(**vars(parser.parse_args(argv)))


def main(argv: Sequence[str] | None = None) -> int:
    """Точка входа console-script ``cast``."""
    # Прогресс идёт вперемешку с ошибками в stderr: без построчного сброса врёт порядок.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(line_buffering=True)
    try:
        args = parse_args(argv)
        command = args.command
        # IUTF8 на stdin включаем на всё время команды и возвращаем режим как было:
        # без него ssh-сессия ломает кириллицу в вопросах.
        with terminal():
            if command == "configure":
                return _cmd_configure(args)
            if command == "stop":
                return _cmd_stop()
            if command == "status":
                return _cmd_status()
            if command == "doctor":
                return _cmd_doctor()
            if command == "log":
                return _cmd_log(args)
            if command == "releases":
                return _cmd_releases(args)
            if command == "voices":
                return _cmd_voices(args)
            if command == "worker":
                return _cmd_worker(str(args.play_key))
            return _cmd_play(args)
    except NotFoundError as exc:
        trace.emit("error", "error", text=str(exc)[:200])
        print(str(exc), file=sys.stderr)
        return EXIT_NOT_FOUND
    except TorrcastError as exc:  # InfraError и всё прочее наше
        trace.emit("error", "error", text=str(exc)[:200])
        print(str(exc), file=sys.stderr)
        return EXIT_INFRA
    except _Stopped:  # `cast stop` - штатный конец показа, а не отказ
        return EXIT_OK
    except KeyboardInterrupt:
        return EXIT_INFRA
    except BrokenPipeError:  # `cast status | head` - не повод показывать трейсбек
        with contextlib.suppress(OSError):
            sys.stdout.close()
        return EXIT_OK
    finally:
        # Дожать хвост следа: фоновый писатель - демон, штатный выход обязан его дождаться.
        trace.shutdown()


def _cmd_configure(args: Args) -> int:
    """``cast --tv <ip>`` — единственная настройка.

    Отдельное значение ``mock`` включает headless-приёмник: так torrcast проверяется без
    телевизора, и адрес ТВ в конфиге при этом отсутствует физически.
    """
    config = load_config()
    config.tv = args.tv
    config.receiver = "mock" if args.tv == "mock" else "chromecast"
    save_config(config)
    note = " (headless-приёмник, каста наружу нет)" if args.tv == "mock" else ""
    print(f"ТВ: {config.tv}{note}")
    return EXIT_OK


def _cmd_stop() -> int:
    """``cast stop`` — снять каст и зафиксировать позицию. Позицию пишет сам
    юнит: ``systemctl stop`` шлёт ему SIGTERM и ждёт, сторож на выходе дописывает state.
    """
    played = unit_active()
    key = unit_key()  # спрашиваем, пока юнит жив: у мёртвого описания уже не узнать
    stop_play_unit()
    found = _shown(State.load(), key)
    if not played or found is None:
        print("ничего не играет")
        return EXIT_OK
    _, entry = found
    print(f"остановлено: «{entry.title}» на {_hms(entry.pos)} / {_hms(entry.dur)}")
    return EXIT_OK


def _shown(state: State, key: str) -> tuple[str, Entry] | None:
    """Запись играющего показа: ключ берём из ``--description`` юнита, а не «самую свежую».
    Рядом мог писать другой ход — тогда свежайшая запись не та, что играет.
    """
    entry = state.get(key) if key else None
    return (key, entry) if entry is not None else state.latest()


def _cmd_status() -> int:
    """``cast status`` — что играет, позиция/длительность, источник. Живой юнит —
    источник правды о факте показа, позиция — из state, куда её кладёт сторож.
    """
    config = load_config()
    playing = unit_active()
    found = _shown(State.load(), unit_key() if playing else "")
    if not playing or found is None:
        print("ничего не играет")
        if found is not None and found[1].resumable:
            print(f"последнее: «{found[1].title}» на {_hms(found[1].pos)} / {_hms(found[1].dur)}")
        return EXIT_OK
    key, entry = found
    what = f"«{entry.title}»" + (f" {entry.label}" if entry.label else "")
    # Разрешение - подтверждённое ffprobe у играющего файла, а не заявка имени.
    what += f" · {entry.quality}" if entry.quality else ""
    print(f"играю {what} - {_hms(entry.pos)} / {_hms(entry.dur)}")
    if entry.warm > 0:
        # Прогрев - это и есть ответ на вопрос «переживёт ли показ обрыв связи», поэтому
        # он стоит в статусе, а не в отладочной ручке.
        whole = entry.dur > 0 and entry.warm >= entry.dur * WARMED_RATIO
        print(
            f"   прогрето {_hms(entry.warm)} из {_hms(entry.dur)}"
            + (" - весь фильм на диске, интернет не нужен" if whole else "")
        )
    where = "адрес раздачи не определён"
    with contextlib.suppress(TorrcastError):  # адреса нет - статус показа это не отменяет
        where = hls_base(config)
    print(
        f"   {key} · файл #{entry.file_idx} · дорожка {entry.audio + 1} · "
        f"раздача {where}, приёмник {config.receiver}"
    )
    return EXIT_OK


def _cmd_releases(args: Args) -> int:
    """``cast releases <запрос>`` — отладочная ручка: старая таблица и выход.

    На счастливом пути таблицы нет вовсе: релиз выбирается сам. Но посмотреть, из чего
    он выбирал, иногда надо — и тогда рядом лежит ``cast <запрос> --release N``.
    """
    config = load_config()
    inner = Args(query=list(args.query[1:]))
    if not inner.query:
        raise NotFoundError("что искать? cast releases <запрос>")
    with Progress() as progress:
        plans = _search(config, inner, progress)
    for plan in plans:
        print()
        print(f"{_named(plan.picture)} - раздач {len(plan.ranked)}")
        print(render_table(plan.ranked, plan.runtime, plan.warn_mbit, recode_at=plan.recode_at))
    print()
    print("играть конкретный: cast <запрос> --release N [--file N]")
    return EXIT_OK


def _cmd_voices(args: Args) -> int:
    """``cast voices <запрос>`` — какие озвучки есть у релиза, который поедет на ТВ.

    Отладочная ручка того же рода, что ``cast releases``: на счастливом пути озвучка
    выбирается сама, а посмотреть, из чего она выбрана, — сюда. Играть конкретную:
    ``cast <запрос> --voice N``.

    Показ отсюда не начинается и состояние не пишется; прогретые раздачи убираются из
    TorrServer, как и на всяком пути мимо показа (:meth:`_Bench.drop_all`).
    """
    config = load_config()
    inner = Args(query=list(args.query[1:]), release=args.release, file=args.file)
    if not inner.query:
        raise NotFoundError("что искать? cast voices <запрос>")
    with Progress() as progress:
        plans = _search(config, inner, progress)
        bench = _Bench(TorrServer(config.torrserver_url), choose=_file_picker(inner))
        try:
            plan = _pick_plan(plans)
            prep = bench.resolve(plan, inner, progress)
        finally:
            bench.drop_all()
    media = prep.found
    remembered = _remembered(State.load(), plan.picture.key, None)
    print()
    print(f"{_named(plan.picture)} - релиз {prep.number}: {_cut(prep.release.title, 60)}")
    print(voices_table(media, media.default_track(), remembered))
    print()
    print("играть конкретную: cast <запрос> --voice N   (выбор запомнится на эту картину)")
    return EXIT_OK


def _cmd_doctor() -> int:
    """``cast doctor`` — самопроверка окружения по-русски.

    Один вызов отвечает на все вопросы, которые иначе приходится проверять руками: терминал и
    локаль (кириллица в вопросах), Prowlarr и TorrServer (есть чем искать и чем
    раздавать), адрес ТВ и его порт 8009 (есть кому играть), ffmpeg с ``readrate``.
    """
    from torrcast.doctor import checkup

    bad = 0
    for line, ok in checkup(load_config()):
        print(line)
        bad += 0 if ok else 1
    print()
    print("всё в порядке" if not bad else f"проблем: {bad} - смотри строки «плохо» выше")
    return EXIT_OK if not bad else EXIT_INFRA


def _cmd_log(args: Args) -> int:
    """``cast log [--since]`` — выжимка недельного диагностического следа.

    По умолчанию - последние три сеанса; ``--since`` двигает границу (``2d``/``12h``/``30m``
    или дата ``ГГГГ-ММ-ДД``) и снимает потолок числа сеансов. Читает ту же ленту, что ведут
    поиск, отбор и показ, - никаких внешних систем, всё лежит рядом с состоянием.
    """
    since = _since_seconds(args.since)
    rows = trace.records(since)
    limit = 0 if args.since else 3
    print(trace.digest(rows, limit=limit))
    return EXIT_OK


def _since_seconds(since: str | None) -> float:
    """``--since`` в абсолютное время: ``2d``/``12h``/``30m`` от сейчас или дата ГГГГ-ММ-ДД."""
    if not since:
        return 0.0
    units = {"d": 86400.0, "h": 3600.0, "m": 60.0}
    tail = since[-1].lower()
    if tail in units and since[:-1].isdigit():
        return time.time() - int(since[:-1]) * units[tail]
    with contextlib.suppress(ValueError, OverflowError):
        return time.mktime(time.strptime(since, "%Y-%m-%d"))  # локальная дата, как и весь след
    return 0.0


def _cmd_worker(key: str) -> int:
    """Показ внутри transient-юнита: своей раздачей, своей упаковкой и своим сторожем.

    Руками не зовётся — это ``ExecStart`` юнита ``torrcast-play``. Всё, что нужно знать о
    показе, лежит в записи состояния: magnet, файл, дорожка и позиция.

    Сериал юнит доигрывает сам: серия дошла до порога 95 % — сторож записал в
    состояние следующую, и цикл берёт её же раздачу и следующий файл, не спрашивая CLI.
    Серия была последней — состояние отмечает конец, цикл выходит, юнит гаснет чисто.

    ⚠️ **Приёмник один на весь юнит, а не на серию.** Соединение с ТВ живёт здесь и
    достаётся каждой серии готовым. Иначе получалось два сендера сразу: на стыке серий
    приложение приёмника намеренно не закрывается (:func:`_handover`), поэтому и сокет
    прошлой серии оставался жив, а следующая поднимала себе новый. Для приёмника оба —
    один и тот же ``sender-0`` (докстринг :class:`torrcast.cast.ChromecastReceiver`), и он
    отвечает новому пустым статусом. Замер на живом Q70D, стык s1e5→s1e6: два
    соединения в ``ss``, «LOAD не взяли (IDLE/ERROR)», «приёмник залип — закрываю
    приложение и соединение», экран пустой **15.3 с**.
    """
    mark("процесс показа")
    config = load_config()
    # SIGTERM от `cast stop` обязан пройти через finally: иначе позиция не запишется.
    signal.signal(signal.SIGTERM, _on_term)
    torrserver = TorrServer(config.torrserver_url)
    receiver = make_receiver(
        config.receiver, config.tv or "", config.hls_cert if config.transport == "https" else ""
    )
    magnet, torrent_hash = "", ""
    while True:
        entry = State.load().get(key)
        if entry is None:
            raise InfraError(f"в состоянии нет записи {key}")
        if entry.magnet != magnet:  # раздача та же - метаданные второй раз не ждём
            magnet = entry.magnet
            torrent_hash = torrserver.add(magnet)
            torrserver.wait_files(torrent_hash, timeout=WORKER_META)
        source = torrserver.stream_url(torrent_hash, entry.file_idx)
        entry = _duration(key, entry, source)
        watch = Watch(key=key, entry=entry)
        title = " ".join(filter(None, (entry.title, entry.label)))
        trace.emit("session", "session_start", title=title, pos=round(entry.pos, 1))
        print(f"показ «{title}» с {_hms(entry.pos)}", flush=True)
        code = _play(
            config,
            source,
            entry.audio,
            title,
            _Clock(),
            watch,
            receiver=receiver,
            codec=entry.codec,
            # Прогрев следующей серии впрок: собирается лениво, когда текущая уже на
            # диске (:meth:`torrcast.warm.Warmer._chain`). Раздача та же, файл - соседний.
            follow=partial(_next_warmer, config, torrserver, torrent_hash, entry),
        )
        following = _following(key) if watch.done else None
        if following is None:
            return code
        print(f"следующая серия: {following.label}", flush=True)


def _following(key: str) -> Entry | None:
    """Серия, которую юнит доиграет следом за только что досмотренной.

    ``None`` — показ на этом кончается: фильм, последняя серия сезона или запись, которую
    сериалом и не считали. Отсюда же знают, закрывать ли приложение приёмника: между
    сериями оно живёт дальше, а на конце показа — гаснет (см. :func:`_play`).
    """
    entry = State.load().get(key)
    if entry is None or entry.done or not entry.label:
        return None
    return entry


def _duration(key: str, entry: Entry, source: str) -> Entry:
    """Длительность серии для порога 95 %: следующая серия своей ещё не знает —
    её длительность лежит в её же файле, и читается она из потока, как дорожки.

    Тем же ffprobe берётся и вес видеодорожки (:attr:`Entry.vbps`): у следующей серии
    он свой, а профиль тяжести показа считается по нему.

    ⚠️ Ради одного только веса дорожки ffprobe тут не зовётся. Записи прежних версий его
    не несут, и спрашивать за них при каждом запуске значило бы платить секундами старта
    (у «Моаны 2» ffprobe стоит до 17 с) за то, что показ и так доберёт по факту
    (:meth:`torrcast.recode.Weights.calibrate`). Своё число такая запись получит на первом
    же обычном запуске через выбор релиза.
    """
    if entry.dur > 0:
        return entry
    media = probe(source, timeout=WORKER_DUR)
    entry.dur = media.duration
    # Ноль - «ещё не спрашивали», минус - «спросили, паспорт промолчал» (mp4 без тегов).
    entry.vbps = media.video_bps / 1e6 or -1.0
    # Кодек следующей серии тоже свой: в раздаче аниме нередко лежат и HEVC, и H.264,
    # а решение «перекодировать целиком» принимается по файлу, который играем сейчас.
    entry.codec = media.video or ""
    state = State.load()
    state.put(key, entry)
    state.save()
    return entry


class _Stopped(KeyboardInterrupt):
    """``cast stop``: SIGTERM пришёл, показ окончен штатно — это не авария.

    Наследуемся от ``KeyboardInterrupt`` намеренно: раскрутка обязана пройти ровно так
    же, как проходила, — через ``finally`` в :func:`_play`, где пишется позиция, гаснет
    упаковка и снимается каст. Меняется только вывеска на выходе: ``cast stop`` — это
    успех, и юнит обязан умереть кодом 0, иначе systemd помечает его ``failed`` и после
    каждой штатной остановки в `systemctl` краснеет `● torrcast-play … failed`.
    """


def _on_term(_signal: int, _frame: object) -> None:
    raise _Stopped


@dataclass(slots=True)
class Watch:
    """Сторож: раз в :data:`WATCH_SECONDS` кладёт позицию приёмника в state.

    Позиция приходит абсолютной: манифест описывает весь фильм, а ``-copyts`` оставляет
    в сегментах исходные метки времени, поэтому приёмник считает время от начала фильма
    независимо от того, с какого места идёт упаковка. Пересчитывать смещение показу
    больше не нужно — раньше это была отдельная строчка возможной лжи.
    Порог 95 % — «досмотрено»: фильму сброс с пометкой, сериалу следующая серия.
    """

    key: str
    entry: Entry
    every: float = WATCH_SECONDS
    done: bool = False
    last: float = field(default_factory=time.monotonic)

    def see(self, pos: float) -> None:
        """Позиция от приёмника; на диск — не чаще раза в ``every`` секунд. Порог 95 %
        записывается сразу: на нём держится стык серий, ждать тика ещё 10 с незачем.
        """
        if pos <= 0:  # приёмник ещё не начал считать - нулём позицию не затираем
            return
        self.entry.pos = pos
        if self.entry.watched or time.monotonic() - self.last >= self.every:
            self.flush()

    def flush(self) -> None:
        """Записать состояние атомарно (tmp + rename в :mod:`torrcast.state`)."""
        if self.done:  # досмотренную запись повторными тиками не портим
            return
        self.last = time.monotonic()
        state = State.load()  # перечитываем: рядом мог писать другой ход
        self.done = self.entry.watched
        state.put(self.key, self.entry.advance() if self.done else self.entry)
        state.save()
        if self.done:
            what = f" {self.entry.label}" if self.entry.label else ""
            print(f"досмотрено{what}: {_hms(self.entry.pos)} из {_hms(self.entry.dur)}", flush=True)


@dataclass(slots=True)
class _Clock:
    """Фазы старта: холодный старт стоит 15–30 с, и цифры должны быть видны глазами."""

    start: float = field(default_factory=time.monotonic)
    last: float = field(default_factory=time.monotonic)

    def lap(self) -> str:
        now = time.monotonic()
        gap, self.last = now - self.last, now
        return f"{gap:.1f} с"

    @property
    def total(self) -> float:
        return time.monotonic() - self.start


def _cmd_play(args: Args) -> int:
    """Счастливый путь: запрос → «какой фильм?» → «какая озвучка?» → показ.

    Релиз и файл выбираются сами, таблиц и списков файлов на этом пути нет. Пока человек
    отвечает на вопрос про франшизу, топ-3 кандидата уже греются в TorrServer и читаются
    ffprobe: к моменту ответа критический путь чаще всего пуст.

    ``--new`` здесь ничего не стирает: сохранённая позиция уходит в расход только тогда,
    когда показ уже точно начинается (:func:`_forget_progress`). Почему так — там же.
    """
    mark("команда")
    clock = _Clock()
    config = load_config()
    state = State.load()
    found_entry = state.find(args.title_query)
    # --new: прежний прогресс не продолжаем и выбираем заново, но запись пока цела.
    stale = found_entry[0] if found_entry is not None and args.new else None
    if found_entry is not None and not args.new:
        code = _continue(config, *found_entry, args=args, clock=clock)
        if code is not None:
            return code

    with Progress() as progress:
        plans = _search(config, args, progress)
        # Справка к меню (рейтинг, хронометраж, о чём кино) едет фоном - ровно в те
        # секунды, что уходят на подъём прогрева. Меню её не ждёт: см. torrcast.facts.
        facts = Facts([(p.picture.title, p.picture.year) for p in plans])
        facts.start()
        torrserver = TorrServer(config.torrserver_url)
        bench = _Bench(torrserver, choose=_file_picker(args))
        # Прогрев под меню: пока идёт вопрос, раздачи уже качают метаданные.
        for plan in warm_order(plans)[:PREWARM]:
            bench.start(plan, plan.first)
        try:
            try:
                plan = _pick_plan(plans, facts)
            finally:
                # Меню уже на экране, и ответ на него получен: пусть фоновый добор допишет
                # кэш - СЛЕДУЮЩЕЕ меню этой франшизы будет полным. Ко времени до меню это
                # отношения не имеет, а к моменту ответа поток обычно давно закончил.
                facts.finish()
            prep = bench.resolve(plan, args, progress)
        except BaseException:  # Ctrl-C, «картин много, а терминала нет», «годного нет»
            bench.drop_all()  # прогретое без показа - мусор в рое и кэш в чужой RAM
            raise
        bench.keep_only(prep)  # прогрев греет лишнее - до показа лишнее убираем

    release, video, media = prep.release, prep.want, prep.found
    audio, voice = pick_voice(media, args, _remembered(state, plan.picture.key, found_entry))
    mark("ответы")  # ноль секундомера: Enter после последнего вопроса
    label = media.tracks[audio].label if audio < len(media.tracks) else "-"
    series = plan.series
    what = f"«{plan.picture.title}»" + (
        f" {series.want}" if series else f" ({plan.picture.year or '?'})"
    )
    about = f"{what} · {quality_text(release, media)} · {label}"
    trace.emit(
        "select",
        "select",
        release=prep.number,
        quality=quality_text(release, media),
        track=label,
        codec=media.video or "",
        mbit=round(bitrate_mbit(video.size, media.duration or plan.runtime), 1),
    )
    # Настоящий битрейт: размер файла серии/фильма на его же длительность, а не оценка.
    peak = bitrate_mbit(video.size, media.duration or plan.runtime)
    if peak > config.bitrate_warn_mbit:
        print(
            f"внимание: ~{peak:.0f} Мбит/с - тяжёлые куски перекодирую на ходу"
            if config.recode
            else f"внимание: ~{peak:.0f} Мбит/с - ресивер на таком битрейте может встать"
        )
    # Молчаливого японского не бывает: перевода в файле нет - человек слышит об этом
    # строкой, а не на слух через минуту показа.
    if note := sound_note(media, audio, plan.ranked, release):
        print(note)
    if args.pinned:  # отладочный путь: тут внутренности показывать и надо
        print(f"файл: {video.base} · {_gb(video.size)} · {_hms(media.duration)} · {media.video}")
    if args.dry:
        print(f"(--dry) {about} - каста нет")
        return EXIT_OK
    entry = Entry(
        title=plan.picture.title,
        magnet=release.magnet,
        kind="tv" if plan.picture.kind == "tv" else "movie",
        file_idx=video.index,
        audio=audio,
        voice=voice,
        dur=media.duration,
        # Вес видеодорожки из паспорта: по нему показ строит профиль тяжести с первой
        # секунды, не набирая поправку «контейнер → ТВ» вслепую.
        vbps=media.video_bps / 1e6 or -1.0,
        # Кодек оттуда же: по нему показ решает, играть копией или перекодировать файл
        # целиком, и решает это один раз - до первого сегмента (:func:`_encode_all`).
        codec=media.video or "",
        # То, что уехало на ТВ: `cast status` покажет факт, а не заявку имени.
        quality=media.quality if media.height else "",
        query=slugify(args.title_query),
        season=series.want.season if series else None,
        episode=series.want.episode if series else None,
        episodes=series.table if series else [],
    )
    if stale is not None:  # точка невозврата пройдена - вот теперь --new вправе забывать
        _forget_progress(stale)
    return _launch(config, plan.picture.key, entry, about, clock)


def _forget_progress(key: str) -> None:
    """Забыть прежний прогресс по ``--new`` — в момент, когда показ уже точно начинается.

    Раньше запись стиралась первым же действием команды, до единого вопроса. Любой обрыв
    после этого — «ничего не разобралось», Ctrl-C, упавший ffprobe, а на прогоне без
    терминала ещё и выбор вслепую — оставлял пользователя без сохранённого места, и взять
    его было неоткуда: state уже перезаписан (ровно так и терялась запись фильма).

    Раннее стирание при этом ничего не давало: свежую запись с нулевой позицией всё равно
    кладёт :func:`_launch`. То есть у него была одна цена и ни одной пользы.
    """
    state = State.load()  # перечитываем: рядом мог писать другой ход
    state.drop(key)
    state.save()


def _search(config: Config, args: Args, progress: Progress) -> list[_Plan]:
    """Поиск и разбор выдачи: запрос → картины франшизы, каждая со своим пулом релизов."""
    from torrcast.parse import THIN_POOL, cluster, pick_franchise

    if not config.prowlarr_apikey:  # без Prowlarr искать нечем - это инфра-ошибка
        raise InfraError("не настроен Prowlarr: apikey пуст, перезапусти ./install.sh")
    query = args.title_query
    name, index = split_franchise_index(query)
    client = Prowlarr(config.prowlarr_url, config.prowlarr_apikey)
    progress.phase(f"поиск «{name}»")
    raw = _ask(client, name)
    pictures = cluster(to_releases(raw))
    # Номер в запросе - позиция во франшизе, а не в общей выдаче.
    found = pick_franchise(query, pictures)
    if max((len(p.releases) for p in found), default=0) < THIN_POOL:
        raw, pictures, found = _second_language(client, query, raw, found, progress)
    # Сериал есть, а раздач нужного сезона в нём нет - добрать сезонной строкой по
    # оригиналу, прежде чем честно отказать (:func:`_season_reinforce`).
    if _lacks_season(found, args):
        raw, pictures, found = _season_reinforce(client, query, args, raw, found, progress)
    mark("поиск", найдено=len(raw))
    trace.emit("search", "query", query=query, raw=len(raw), pictures=len(pictures))
    if not raw:
        raise NotFoundError(f"по запросу «{name}» ничего не нашлось")
    if not pictures:
        raise NotFoundError(f"по запросу «{name}» ничего не разобралось")
    if not found:
        raise NotFoundError(_nothing(name, index, pictures))
    lead = _leading(found)
    if other := other_words(name, lead):
        progress.note(f"«{name}» - в каталоге это «{other}»")
    if lead is not None and lead.also:
        # Склейка картин (:func:`~torrcast.parse.glue`) - решение автоматическое, и молчать
        # о нём нельзя: человек спросил одно имя, а в меню и в отборе теперь оба.
        progress.note(f"«{lead.also}» и «{lead.title}» - одна картина, раздач {len(lead.releases)}")
    progress.phase("")
    # Номер пункта меню человек читает как номер части и им же отвечает: «Тачки 2» обязаны
    # стоять вторыми, а безномерные - после линейки (:func:`~torrcast.parse.menu_order`).
    found = menu_order(found)
    plans = [plan for plan in (_plan_for(p, args, config) for p in found) if plan.ranked]
    # Соседи по франшизе, до меню не доехавшие: понадобятся, если у выбранной картины
    # годного релиза не окажется вовсе (:func:`kin_line`).
    kin = _kin(_leading(found), pictures, {plan.picture.key for plan in plans})
    for plan in plans:
        plan.kin = kin
    if not plans:  # картина есть, а раздач нужного сезона в ней нет
        want = args.episode or Episode(1, 1)
        raise NotFoundError(f"«{found[0].title}»: раздач с сезоном {want.season} нет")
    return plans


#: Сколько соседей по франшизе называем в строке отказа. Больше не помещается в строку, да
#: и незачем: это подсказка, а не второй список - список человек уже получит по `cast`.
KIN_SHOWN: Final = 3


def _kin(picture: Picture | None, pictures: list[Picture], shown: set[str]) -> list[Picture]:
    """Части франшизы, до меню не доехавшие, но в каталоге живые.

    Не доехать часть могла по-разному: запрос попал в свою половину двуязычной франшизы,
    или у картины не осталось ни одного релиза, прошедшего отбор. Обещать за них ничего
    нельзя - поэтому строка отказа говорит ровно «в каталоге есть», а не «возьми это».
    """
    from torrcast.parse import franchise_name, pick_franchise

    if picture is None:
        return []
    whole = pick_franchise(franchise_name(picture.title), pictures)
    return [p for p in whole if p.key not in shown and p.key != picture.key and p.releases]


def kin_line(kin: list[Picture]) -> str:
    """«в каталоге есть Тачки 2 (2011), Тачки 3 (2017) - cast тачки 2». Пусто - молчим.

    Строка-подсказка, и только: сама другую часть не запускает. Человек просил «cast
    cars», у этой картины годного релиза не нашлось - и подменить её соседкой по франшизе
    значило бы показать не то, что просили. А вот промолчать о живых соседях, отправив
    человека разбираться руками, - это скрыть то, что мы уже знаем.
    """
    if not kin:
        return ""
    names = ", ".join(f"{p.title} ({p.year or '?'})" for p in kin[:KIN_SHOWN])
    return f"в каталоге есть {names} - cast {kin[0].title.casefold()}"


def _nothing(name: str, index: int | None, pictures: list[Picture]) -> str:
    """Почему ответа нет. Причины две, и человеку с ними делать разное.

    Прежде обе накрывались одной строкой - «такой картины во франшизе нет». Она честна
    ровно в одном случае из двух: когда франшизу нашли, а нужной части в ней не оказалось.
    В остальных выдача не содержала вообще ничего похожего на запрос («дети мужчин» - это
    ``Children of Men``, в каталоге такого имени нет вовсе), и строка про франшизу
    отправляла человека проверять номер части там, где не нашлось и самого фильма.

    Разводим по факту: спрашивали ли номер и стоит ли за ним живая франшиза.

    * франшиза есть, номера в ней нет → сколько в ней картин и что номера столько нет;
    * во всём остальном → честное «ничего не нашлось», то есть «назови другими словами».
    """
    from torrcast.parse import pick_franchise

    whole = pick_franchise(name, pictures) if index is not None else []
    if whole:
        return f"«{name}»: картин во франшизе {len(whole)}, номера {index} нет"
    return f"по запросу «{name}» ничего не нашлось"


def _ask(client: Prowlarr, query: str) -> list[RawResult]:
    """Один запрос к индексерам; пусто - это не ошибка, а повод переспросить иначе."""
    try:
        return client.search(query)
    except NotFoundError:
        return []


def _second_language(
    client: Prowlarr,
    query: str,
    raw: list[RawResult],
    found: list[Picture],
    progress: Progress,
) -> tuple[list[RawResult], list[Picture], list[Picture]]:
    """Русский запрос дал пусто или тощий пул - переспросить тем же названием на латинице.

    Индексер ищет по имени раздачи, поэтому «Психо» приносит десяток русских имён, а
    сорок раздач ``Psycho.1960.*`` остаются за бортом - и человек либо смотрит 576p, либо
    (как на «Птицах») не получает ни одного годного релиза. Догадываться, что надо
    набрать латиницей, он не обязан: название на латинице лежит в первой же выдаче,
    :func:`~torrcast.parse.alt_query` его оттуда и достаёт.

    Второй заход стоит ещё одного круга по индексерам, поэтому он не всегда, а только на
    тощем пуле: на полной выдаче (порог :data:`~torrcast.parse.THIN_POOL`) поиск остаётся
    ровно таким, каким был. Цена круга - обычно 0.5-1.5 с, но ровно та же, что у первого:
    если индексер молчит, круг стоит его личного бюджета
    (:data:`~torrcast.search._INDEXER_TIMEOUT`), и тогда добор виден человеку секундами
    ожидания. Обещать «1-3 с» тут нельзя: замеры на живом стенде давали и 101.6-102.1 с -
    столько круг стоил, пока молчание одного индексера ждали общим запросом.

    Запросы идут последовательно, а не парой: второе имя достаётся из ПЕРВОЙ выдачи, до
    неё его просто нет. И уж точно не тем же именем: на латинском запросе оригинал из
    выдачи совпадает с самим запросом, и круг уходил целиком впустую - на живом стенде
    это стоило 102 секунды до меню.

    Строка вердикта печатается ПОСЛЕ строки того круга, о котором она говорит: ``note``
    выходит сразу, а строка фазы - только когда фазу закрыли, и в прежнем порядке «не
    беру» стояло перед «поиск… 102.1 с». Читалось это как противоречие: сначала отказ,
    а следом будто бы удавшийся второй поиск, из которого и выросло меню.

    Выдачи склеиваются, а не заменяются: русские имена несут озвучки и оригинал, по
    которому кластер и сшивает оба языка в одну картину. Если добор ничего не дал или
    картину после него не нашли, остаётся прежний результат - хуже стать не может.

    🔴 **Гейт: добор не вправе подменить картину.** Русское имя картину не определяет.
    «Восхождение» - это и фильм Шепитько 1977 года, и китайский 2019-го, подписанный
    тем же словом; оригинал ``The Climbers`` лежал прямо в русской выдаче, добор
    переспрашивал им и приносил два десятка раздач чужого кино с дорожкой ``und``.
    Раздач становилось больше, прежней проверке этого хватало, и человек молча получал
    не тот фильм. Поэтому мало «стало больше» - сверяется САМА КАРТИНА:

    * год у справки (:func:`~torrcast.facts.origin`) - она отвечает про ту картину, что
      спросили, и её слово сильнее выдачи;
    * год картины, за которой шли ДО добора, - если справки нет, годится и он;
    * франшиза - когда года не назвал никто.

    ⚠️ Год справки не в счёт, когда в запросе назван номер части: справку зовут по имени
    франшизы, и год она называет первой картины, а спрашивали другую.

    Расхождение или сомнение - добора не было. Честное «не нашлось» лучше чужого фильма,
    и это не перестраховка: подмену видно только по году, потому что кластер сшивает
    одноимённые картины в одну франшизу и «стало больше» у неё выходит честным.
    """
    from torrcast.parse import alt_query, cluster, pick_franchise, slugify

    name, index = split_franchise_index(query)
    pool = [r for p in found for r in p.releases] or to_releases(raw)
    lead = _leading(found)
    # Справку спрашиваем вслепую: год выдачи ей не сообщаем, иначе она подстроится под него
    # и сверять станет нечего. Тип картины - другое дело, у сериала и фильма разные статьи.
    # Русская выдача пуста - тип брать неоткуда: тогда series=None, и справка пробует оба и
    # верит лишь согласию (иначе неверный тип уводит в чужую статью). Сети нет - паспорт
    # пуст, и всё дальше работает ровно так, как работало.
    about = origin(name, series=(lead.kind == "tv") if lead else None)
    if index is not None:
        # 🔴 Спросили номер части - год справки к делу не относится. Справку зовут по имени
        # франшизы, и отвечает она про её ПЕРВУЮ картину: у «тачек» это 2006 год, а человек
        # просил «тачки 2» - картину 2011-го. Гейт читал это расхождение как подмену и
        # выбрасывал честную выдачу; на живом стенде «тачки 2» так и не находились вовсе.
        # Название латиницей остаётся: номер части у него всё равно отрезан, и оно верное.
        about = Origin(title=about.title, name=about.name)
    alt = alt_query(name, pool, about.title, about.name)
    # Тем же именем второй раз ходить незачем: на «cast cars» оригинал из выдачи - «Cars»,
    # и это ещё один полный круг по всем индексерам (на живом стенде - до 102 секунд, если
    # в круге кто-то молчит) ради той же самой выдачи. Регистр и разделители имя не меняют,
    # поэтому сверяем по слагу.
    if not alt or slugify(alt) == slugify(name):
        return _as_is(raw, found, about, progress)
    progress.phase(f"поиск «{alt}»")
    merged = merge(raw, _ask(client, alt))
    # Круг кончился - закрываем его строку прямо здесь. Всё, что скажем дальше, это его
    # итог, а `note` печатается сразу, тогда как строка фазы ждёт закрытия фазы: без этого
    # вердикт «не беру» выходил ПЕРЕД строкой «поиск «Cars»... 102.1 с», и человек читал два
    # несвязанных сообщения как противоречие - отказ, а следом будто бы удавшийся поиск.
    progress.phase("")
    if len(merged) == len(raw):
        return _as_is(raw, found, about, progress)
    pictures = cluster(to_releases(merged))
    # Спрашивали по-русски - им и выбираем; кластер сшил оба языка, так что название
    # на латинице нужно лишь там, где русских имён в выдаче не оказалось вовсе.
    wider = pick_franchise(query, pictures) or pick_franchise(
        f"{alt} {index}" if index else alt, pictures
    )
    was = sum(len(p.releases) for p in found)
    now = sum(len(p.releases) for p in wider)
    if now <= was:
        # Прибавка не в раздачах картины, а в чужих строках выдачи: широкий пул сдвинул бы
        # нумерацию франшизы («дилижанс 1» уехал бы с 1939 года на 1936) и ничего не дал
        # взамен. Тогда второго захода как будто и не было.
        return _as_is(raw, found, about, progress)
    # Транслит - это сами слова запроса, чужого фильма он принести не может; оригинал из
    # справки отвечает про ту самую картину. А вот оригинал из выдачи ничем не подтверждён.
    proven = bool(about.title) or alt == about.name or alt == transliterate(name)
    # Имя добора от справки - она отвечает про ТУ САМУЮ картину, и спор идёт лишь о том,
    # доехала ли картина нужного года. Имя из выдачи ничем не подтверждено - там гейт строг
    # и сверяет вожака: именно он станет ответом.
    after = _twin(wider, about, lead) if proven else _leading(wider)
    if not same_picture(lead, after, about, proven):
        progress.note(f"по «{alt}» приехала другая картина - остаюсь на выдаче по «{name}»")
        return _as_is(raw, found, about, progress)
    progress.note(f"по-русски раздач {was} - добрал по «{alt}»: стало {now}")
    return merged, pictures, wider


def _as_is(
    raw: list[RawResult], found: list[Picture], about: Origin, progress: Progress
) -> tuple[list[RawResult], list[Picture], list[Picture]]:
    """Добора не было - остаётся то, что нашёл русский запрос. Если это вообще та картина.

    Отменить один добор мало: под именем «Восхождение» в каталоге лежит только китайская
    картина 2019 года, и без второго захода она всё равно осталась бы ответом - просто в
    трёх раздачах вместо десяти. Поэтому здесь работает то же слово справки: она знает,
    что «Восхождение» - это 1976 год, а раз под этим именем в выдаче другое кино, то
    нашей картины в каталоге нет. Так и говорим.

    ⚠️ Условия узкие нарочно. Отбирается ОДНА картина - та, что нашлась под этим именем в
    единственном числе. Во франшизе справка отвечает про первую часть, а в каталоге может
    лежать вторая: на «моане 2» широкий вариант этой проверки честную выдачу и выкидывал.
    Не знает года справка, картин несколько, годы сходятся - никого не трогаем.
    """
    from torrcast.parse import cluster

    stays = (raw, cluster(to_releases(raw)), found)
    if about.year is None or len(found) != 1 or found[0].year is None:
        return stays
    if abs(found[0].year - about.year) <= 1:
        return stays
    # Тот же оригинал - ремейк, а не другая картина: справка знает «Fruits Basket» 2006, в
    # каталоге ремейк 2019, и это одна и та же вещь. Чужой оригинал год по-прежнему разводит.
    if found[0].original and slugify(found[0].original) == slugify(about.title):
        return stays
    progress.phase("")  # вердикт - итог уже законченного круга, и печатается после него
    progress.note(
        f"под этим именем в каталоге лежит картина {found[0].year} года, а не {about.year}"
    )
    return raw, cluster(to_releases(raw)), []


def _lacks_season(found: list[Picture], args: Args) -> bool:
    """Сериал найден, а раздач нужного сезона в нём нет ни по одному имени.

    Ровно тот случай, где отбор упирался в «раздач с сезоном N нет»: TC-6 берёт сезон-пак,
    КОГДА он есть в выдаче, но у части западных сериалов («Ангел») русский запрос не
    приносит ни одной раздачи с нужным сезоном - пак лежит под оригинальным именем со
    строкой сезона (``Angel S01``), до которой русское слово не достаёт. Проверяем по
    именам (:meth:`Release.covers`), без похода в рой: имя пака сезон называет само.
    """
    tv = [p for p in found if p.kind == "tv"]
    if not tv:
        return False
    want = args.episode or Episode(1, 1)
    return not any(r.covers(want.season) for p in tv for r in p.releases)


def _season_reinforce(
    client: Prowlarr,
    query: str,
    args: Args,
    raw: list[RawResult],
    found: list[Picture],
    progress: Progress,
) -> tuple[list[RawResult], list[Picture], list[Picture]]:
    """Добрать сезон-пак сезонной строкой по оригиналу, прежде чем честно отказать.

    Родня транслит-добору (:func:`_second_language`), но повод другой: там пул тощий и
    добираем ЛЮБЫЕ раздачи, здесь пул может быть и полным, а не хватает раздач ровно
    нужного СЕЗОНА. Индексер ищет по имени раздачи, поэтому сезон-пак «Angel [S01-05]»
    русское «ангел» не приносит - его находит строка ``Angel S01`` по оригиналу.

    🔴 **Гейт против подмены.** Добор не пересобирает выдачу как попало: из ответа сезонной
    строки берутся ТОЛЬКО раздачи, у которых оригинал совпадает с оригиналом найденного
    сериала И имя которых называет нужный сезон. Без этого «Angel S01» натащил бы десяток
    чужих аниме («The Angel Next Door ... S01»): у них другой оригинал, и фильтр их
    отсекает. Сама картина после этого выбирается прежним :func:`~torrcast.parse.pick_franchise`.

    Один лишний круг по индексерам, и только когда сезона в выдаче не было вовсе
    (:func:`_lacks_season`): на счастливом пути добора нет. Ничего не подошло - остаётся
    прежний результат, дальше честное «раздач с сезоном N нет».
    """
    from torrcast.parse import cluster, pick_franchise, slugify, transliterate

    name, _index = split_franchise_index(query)
    want = args.episode or Episode(1, 1)
    lead = max((p for p in found if p.kind == "tv"), key=lambda p: len(p.releases), default=None)
    if lead is None:
        return raw, cluster(to_releases(raw)), found
    base = (lead.original or origin(name, series=True).title or transliterate(name)).strip()
    season_query = f"{base} S{want.season:02d}" if base else ""
    # Тем же именем второй раз ходить незачем: если оригинала нет и транслит совпал с
    # запросом, сезонная строка это тот же круг по индексерам ради той же выдачи.
    if not base or slugify(season_query) == slugify(name):
        return raw, cluster(to_releases(raw)), found
    progress.phase(f"поиск «{season_query}»")
    extra = _ask(client, season_query)
    progress.phase("")
    want_orig = slugify(lead.original or base)
    # Берём лишь раздачи ТОГО ЖЕ оригинала и ровно нужного сезона: чужое одноимённое
    # (аниме «The Angel Next Door») по оригиналу не проходит.
    keep = [
        row
        for row, rel in zip(extra, to_releases(extra), strict=True)
        if rel.original and slugify(rel.original) == want_orig and rel.covers(want.season)
    ]
    merged = merge(raw, keep) if keep else raw
    if len(merged) == len(raw):
        return raw, cluster(to_releases(raw)), found
    pictures = cluster(to_releases(merged))
    wider = pick_franchise(query, pictures)
    progress.note(f"сезона {want.season} в выдаче не было - добрал по «{season_query}»")
    return merged, pictures, wider


def _leading(pictures: list[Picture]) -> Picture | None:
    """Картина, за которой идут: самая полная из найденных.

    Именно она - дефолт меню и она же играет, когда терминала нет. Гейт добора смотрит на
    неё, а не на список целиком: список одноимённых картин от добора и должен пополняться,
    а вот вожак меняться не должен.
    """
    return max(pictures, key=lambda p: len(p.releases), default=None)


def _twin(pictures: list[Picture], about: Origin, before: Picture | None) -> Picture | None:
    """Кого из приехавших после добора сверять с той картиной, за которой шли.

    Не самого многолюдного: добор по русскому имени приносит ФРАНШИЗУ целиком, и вожаком
    в ней становится самая раздаваемая часть. На «cars» это «Тачки 3» (14 раздач против
    четырёх у «Тачек» 2006 года), гейт читал 2017 против 2006 как подмену и выбрасывал
    ровно ту выдачу, за которой ходил: человек оставался с одной мёртвой англоязычной
    раздачей при живых русских.

    Поэтому сверяется картина ТОГО ЖЕ ГОДА - года справки, а её нет, так года той картины,
    за которой шли. Нет среди приехавших картины нужного года - сверять идёт вожак.

    🔴 Зовётся это только на ДОКАЗАННОМ имени добора (справка), и в этом вся его
    безопасность: справка отвечает про ту самую картину, поэтому вопрос к добору один -
    доехала ли она. Имя, подобранное из выдачи, не доказывает ничего: под ним приезжает
    однофамилец («Восхождение» - и фильм Шепитько, и китайский ``The Climbers``), и там
    сверяется вожак, то есть тот, кто станет ответом.
    """
    year = about.year if about.year is not None else (before.year if before else None)
    if year is not None:
        near = [p for p in pictures if p.year is not None and abs(p.year - year) <= 1]
        if near:
            return max(near, key=lambda p: len(p.releases))
    return _leading(pictures)


def same_picture(
    before: Picture | None, after: Picture | None, about: Origin, proven: bool
) -> bool:
    """Та же ли картина возглавляет выдачу после добора.

    Год из справки - последнее слово: она отвечает про картину, которую спросили, и если
    вожак после добора другого года, значит приехал однофамилец. Справки нет - сверяем с
    годом того, за кем шли. Годов не назвал никто (сериалы часто без года) - остаётся
    франшиза: подмену она не ловит, но и врать не будет, а без года подменять по сути
    нечего - раздачи неотличимы, и кластер всё равно свёл бы их в одну картину.

    Год ± 1 - это не послабление, а разница между годом производства и годом проката:
    её раздачи путают постоянно, и на ней гейт спотыкался бы о честный добор.

    Отдельный случай - ``before is None``: русский запрос не нашёл ни одной картины, и
    сверять добор не с чем. Тогда решает происхождение названия (``proven``): справка и
    транслит говорят о том, что спросили, а вот непроверенному оригиналу из выдачи в
    пустоту веры нет - «не нашлось» честнее наугад взятого однофамильца.
    """
    if after is None:
        return False
    # Ремейк или переиздание с тем же оригиналом - та же картина, хоть годы и врозь:
    # справка знает «Fruits Basket» 2006, а у индексеров ремейк 2019, и это добор, а не
    # подмена. Спорит с годом только совпадение самого ОРИГИНАЛА: русское имя картину не
    # определяет, а чужой оригинал («The Climbers» против «The Ascent») год по-прежнему
    # разводит - дыру для настоящих подмен это не открывает.
    if about.title and after.original and slugify(after.original) == slugify(about.title):
        return True
    if about.year is not None and after.year is not None:
        return abs(after.year - about.year) <= 1
    if before is None:
        return proven
    if before.year is not None and after.year is not None:
        return abs(after.year - before.year) <= 1
    return franchise_key(before.title) == franchise_key(after.title)


def _plan_for(picture: Picture, args: Args, config: Config) -> _Plan:
    """План по одной картине: пул релизов в порядке отбора и цель для сериала."""
    from torrcast.stream import RUNTIME_GUESS

    series = _Series(want=args.episode or Episode(1, 1)) if picture.kind == "tv" else None
    runtime = RUNTIME_GUESS.get(picture.kind, 7200.0)
    pool = picture.releases
    if series is not None:
        pool = [r for r in pool if r.covers(series.want.season)]
    # Потолок отбора - уже не потолок декодера. Тяжёлые куски перекодируются
    # (:mod:`torrcast.recode`), поэтому честный тяжёлый 1080p теперь берётся, а отбраковывает
    # только то, что перекодированием не спасти, - ``bitrate_hard_mbit``. Перекодирование
    # выключено - потолком снова становится прежний ``bitrate_warn_mbit``.
    ceiling = config.bitrate_hard_mbit if config.recode else config.bitrate_warn_mbit
    want = series.want if series else None
    loose = gate_open(pool, runtime, ceiling, want)
    ranked = rank_releases(pool, runtime, ceiling, want=want, loose=loose)
    return _Plan(
        picture=picture,
        ranked=ranked,
        runtime=runtime,
        warn_mbit=ceiling,
        series=series,
        recode_at=config.recode_at_mbit if config.recode else 0.0,
        loose=loose,
    )


@dataclass(slots=True)
class _Plan:
    """Что покажем по одной картине: пул релизов и, для сериала, нужная серия.

    План строится на **все** картины франшизы ещё до вопроса — иначе прогрев под меню
    невозможен: греть надо то, что человек, скорее всего, выберет.
    """

    picture: Picture
    ranked: list[Release]
    runtime: float
    #: Потолок ОТБРАКОВКИ, Мбит/с: выше него релиз не берём вовсе (см. :func:`_plan_for`).
    warn_mbit: float
    series: _Series | None = None
    #: Порог ПЕРЕКОДИРОВАНИЯ, Мбит/с: выше него куски перекодируются, а релиз годен.
    #: Ноль - перекодирование выключено, и тогда отбраковка и порог это одно число.
    recode_at: float = 0.0
    #: Ворота отбора открыты: живых именных кандидатов у картины нет (:func:`gate_open`),
    #: и молчаливые имена идут в очередь наравне с именными.
    loose: bool = False
    #: Другие части той же франшизы, до меню не доехавшие: их нет в списке картин, но в
    #: выдаче они есть и раздачи у них живые. Нужны одной строке отказа (:func:`kin_line`).
    kin: list[Picture] = field(default_factory=list)

    @property
    def first(self) -> int:
        """Номер релиза, который берём по умолчанию: он же верх :func:`rank_releases`."""
        return 1

    def candidates(self, args: Args) -> list[int]:
        """Очередь релизов: сначала дефолт, потом годные запасные — **все, сколько есть**.

        Обрезать очередь тут больше нечем: сколько раздач успеет разобрать показ, решают
        не эти строки, а :meth:`_Bench.resolve` — по приговорам (:data:`MAX_TRIES`) и по
        часам (:data:`PICK_BUDGET`). Пока очередь резалась тремя номерами, отбор сдавался
        со словами «годного релиза нет» ровно тогда, когда рядом в ней стояли живые: в
        замере на тысяче запросов перепроверка в один поток оживляла шесть картин из
        восьми, у которых три раздачи подряд промолчали пирами.

        Огрызков в очереди нет вовсе (:func:`misses_episode`): тратить на них метаданные
        по DHT незачем — раздача уже своим именем сказала «нужной серии тут нет», и это
        5-40 с за заранее известный отказ. Отбраковка не молчаливая: кого выкинули,
        печатает :attr:`skipped`.

        При открытых воротах (:attr:`loose`) в очередь идут и молчаливые имена: у
        картины иначе нет ни одного живого кандидата, а судить молчание всё равно
        может только ffprobe — и он его тут же и судит.
        """
        if args.release is not None:
            if not 1 <= args.release <= len(self.ranked):
                raise NotFoundError(f"релизов {len(self.ranked)}, номера {args.release} нет")
            return [args.release]
        queue = [self.first]
        queue += [
            n
            for n, r in enumerate(self.ranked, start=1)
            if n != self.first
            and is_candidate(r, self.runtime, self.warn_mbit, self.loose)
            and not misses_episode(r, self.want)
        ]
        return queue

    @property
    def want(self) -> Episode | None:
        """Нужная серия, если картина — сериал; у фильма серии нет."""
        return self.series.want if self.series else None

    @property
    def skipped(self) -> list[Release]:
        """Раздачи, отбракованные до каста: нужной серии в них нет по их же именам."""
        return [r for r in self.ranked if misses_episode(r, self.want)]


@dataclass(slots=True)
class _Series:
    """Серии выбранной раздачи: файлы → ``sNeM``, нужный файл и кэш для состояния.

    Пак это или один сезон — решают ФАЙЛЫ, а не имя раздачи: сколько сезонов нашлось в
    путях, столько и будет в списке, и прыжок `s2e5` внутри пака обойдётся без поиска.
    """

    want: Episode
    files: list[EpisodeFile] = field(default_factory=list)

    def choose(self, release: Release, files: list[TorrFile]) -> TorrFile:
        """Файл нужной серии; такой серии в раздаче нет — честная строка со списком."""
        self.files = map_episodes(files, release.season)
        found = next((f for f in self.files if f.at == self.want), None)
        if found is None:
            raise NotFoundError(
                f"серии {self.want} в этой раздаче нет ({self.summary()}) - "
                "возьми другую раздачу: cast <запрос> --release N"
            )
        return next(f for f in files if f.index == found.index)

    @property
    def table(self) -> list[list[int]]:
        """Список серий для состояния: по нему идут автопереход и прыжки."""
        return [[f.season, f.episode, f.index] for f in self.files]

    def summary(self) -> str:
        """«серий 10: s1e1…s1e10», для пака — ещё и диапазон сезонов."""
        if not self.files:
            return "серий не нашлось"
        seasons = {f.season for f in self.files}
        span = f"сезоны {min(seasons)}-{max(seasons)} · " if len(seasons) > 1 else ""
        return f"{span}серий {len(self.files)}: {self.files[0].at}...{self.files[-1].at}"


def _continue(config: Config, key: str, entry: Entry, args: Args, clock: _Clock) -> int | None:
    """Продолжение по сохранённому выбору. ``None`` — состоянием не обойтись,
    дальше идёт обычный путь с поиском и меню.

    Сериал вопросов не задаёт вовсе: релиз, дорожка и список серий уже выбраны, а
    какую серию и с какого места играть — записано. Фильм спрашивает ровно одно.
    """
    if not entry.serial:  # фильм (в том числе ошибочно записанный сериалом) - один вопрос
        if not entry.resumable:
            return None  # продолжать нечего - озвучку выберет обычный путь, по дорожкам
        return _resume(config, key, _voiced(config, entry, args), clock=clock, dry=args.dry)
    entry = _voiced(config, entry, args)
    if args.episode is not None:  # `cast киберпанк s2e5` - прыжок по кэшу раздачи
        jumped = entry.jump(args.episode.season, args.episode.episode)
        if jumped is None:
            return None  # серии в этой раздаче нет - честно идём искать релиз сезона
        return _launch(config, key, jumped, _about(jumped), clock, args.dry)
    if entry.done:  # конец раздачи: сама собой следующая серия не появится
        print(f"«{entry.title}» - {entry.label} была последней в раздаче")
        if ask_line("Смотреть сначала? [Да/нет]")[:1] in {"н", "n"}:
            return EXIT_OK
        first = entry.episodes[0]
        entry = entry.jump(first[0], first[1]) or entry
    return _launch(config, key, entry, _about(entry), clock, args.dry)


def _remembered(state: State, key: str, found: tuple[str, Entry] | None) -> str:
    """Озвучка, которую пользователь выбирал для этой картины.

    Смотрим по каноническому ключу картины — под ним показ и пишет запись. Запись,
    найденную по тексту запроса (:meth:`State.find`), берём запасным вариантом: у
    одной картины в состоянии могут лежать записи разных запросов («moana» и «моана»),
    и память озвучки не должна зависеть от того, как её позвали в прошлый раз.
    """
    entry = state.get(key) or (found[1] if found is not None else None)
    return entry.voice if entry is not None else ""


def _voiced(config: Config, entry: Entry, args: Args) -> Entry:
    """Запись с учётом ``--voice``; без флага — она же, не тронутая и без похода в рой.

    Флага нет — не читаем ничего: этот путь тем и хорош, что обходится состоянием.
    ⚠️ Звать только тогда, когда запись действительно пойдёт в показ. Живая грабля:
    вызов до проверки «есть ли что продолжать» лез в TorrServer за раздачей,
    которую никто играть не собирался, и падал на её магните.
    """
    return entry if args.voice is None else _revoice(config, entry, args)


def _revoice(config: Config, entry: Entry, args: Args) -> Entry:
    """``--voice`` поверх сохранённого выбора: перечитать дорожки раздачи и взять нужную.

    Нужно ровно для сериала и продолжения: там показ идёт по записи состояния и потока
    никто не читает — ни номеров дорожек, ни подписей взять неоткуда. Платим за это
    метаданными раздачи и одним ffprobe (секунды, с живым прогрессом), и платим только
    когда флаг назван: счастливый путь этой цены не видит.

    Состояние отсюда не пишется: выбор уезжает в запись показа (:func:`_launch`) вместе
    с позицией и серией. Так у ``--dry`` не остаётся следов, а память не переписывается
    показом, который не начался.
    """
    torrserver = TorrServer(config.torrserver_url)
    with Progress() as progress:
        progress.phase("дорожки")
        torrent_hash = torrserver.add(entry.magnet)
        torrserver.wait_files(torrent_hash, timeout=META_BUDGET)
        media = probe(torrserver.stream_url(torrent_hash, entry.file_idx), timeout=PROBE_BUDGET)
        progress.phase("")
    entry.audio, entry.voice = pick_voice(media, args, entry.voice)
    return entry


def _about(entry: Entry) -> str:
    """Строка показа по записи состояния: «Киберпанк» · s1e2 · дорожка 1 · с 0:03:20."""
    voice = entry.voice or f"дорожка {entry.audio + 1}"
    parts = [f"«{entry.title}»", entry.label, entry.quality, voice]
    if entry.pos > 0:
        parts.append(f"с {_hms(entry.pos)}")
    return " · ".join(filter(None, parts))


@dataclass(slots=True)
class _Prep:
    """Подготовка одного релиза целиком в фоне: раздача, файл, дорожки.

    Это и есть прогрев под меню. Фазы идут своим ходом в отдельном потоке, а показ
    спрашивает только результат — поэтому 17 секунд ffprobe на «Моане 2» уходят из
    критического пути в паузу между вопросами.

    Каждая фаза имеет **бюджет**: не уложилась — это не «зависло насмерть» без единого
    слова, а :attr:`error` и следующий релиз в очереди.
    """

    number: int
    release: Release
    torrent_hash: str = ""
    #: Прогрев оказался ненужным: показ ушёл на другую картину или другой релиз. Такая
    #: раздача убирается из TorrServer сразу - иначе два лишних торрента тянули бы кэш
    #: и полосу у самого показа.
    dropped: bool = False
    video: TorrFile | None = None
    media: Media | None = None
    error: str = ""
    phase: str = "очередь"
    started: float = field(default_factory=time.monotonic)
    meta: float = 0.0
    read: float = 0.0
    ready: threading.Event = field(default_factory=threading.Event)

    @property
    def want(self) -> TorrFile:
        if self.video is None:
            raise InfraError("файл раздачи не выбран")
        return self.video

    @property
    def found(self) -> Media:
        if self.media is None:
            raise InfraError("поток не прочитан")
        return self.media

    @property
    def timing(self) -> str:
        return f"метаданные {self.meta:.1f} с, дорожки {self.read:.1f} с"


class _Bench:
    """Прогрев релизов: несколько раздач готовятся разом, показ берёт первую годную.

    Держит по потоку на релиз и умеет ждать нужный с живым прогрессом. Любая осечка
    (нет пиров, не читается поток, оказался HEVC) стоит одной строки и перехода к
    следующему кандидату — молчаливых подмен и молчаливых зависаний не бывает.
    """

    def __init__(
        self,
        torrserver: TorrServer,
        choose: Callable[[_Plan, Release, list[TorrFile]], TorrFile] | None = None,
        meta_budget: float = META_BUDGET,
        probe_budget: float = PROBE_BUDGET,
    ) -> None:
        self.torrserver = torrserver
        self.choose = choose or _default_file
        self.meta_budget = meta_budget
        self.probe_budget = probe_budget
        self.preps: dict[tuple[str, int], _Prep] = {}

    def start(self, plan: _Plan, number: int) -> _Prep:
        """Начать (или вернуть уже начатую) подготовку релиза ``number`` этого плана."""
        key = (plan.picture.key, number)
        found = self.preps.get(key)
        if found is not None:
            return found
        prep = _Prep(number=number, release=plan.ranked[number - 1])
        self.preps[key] = prep
        threading.Thread(target=self._work, args=(plan, prep), daemon=True).start()
        return prep

    def resolve(self, plan: _Plan, args: Args, progress: Progress) -> _Prep:
        """Годный релиз плана: ждём подготовку с прогрессом, негодный — следующий.

        Осечки бывают двух разных сортов, и до сих пор они стоили одинаково — попытки из
        трёх:

        * **приговор** — ffprobe раздачу прочитал и она не годится (av1, vc1, тяжёлая).
          Про релиз узнали всё, второй раз спрашивать нечего;
        * **молчание роя** — метаданные не приехали, поток не прочитался, фаза не
          уложилась в бюджет. Про КАЧЕСТВО релиза при этом не узнали ничего: раздача
          просто не отозвалась.

        Считать их одинаково — это и есть главная причина 🟡 в замере на тысяче запросов:
        три подряд «нет пиров за 20 с» заканчивали отбор словами «годного релиза нет»,
        хотя ниже в очереди стояли живые. Перепроверка тех же картин в один поток
        оживляла шесть из восьми («Кавказская пленница», «Зона интересов», «Бесконечная
        история»).

        Поэтому попытку жжёт только приговор (:data:`MAX_TRIES`), а молчание роя — часы
        (:data:`PICK_BUDGET`). Бесконечно это не длится и молчаливым не бывает: потолок
        фазы прежний, каждая осечка стоит строки, а очередь конечна.
        """
        queue = plan.candidates(args)
        if args.release is None and (skipped := plan.skipped):
            # Молчать тут нельзя: человек попросил серию, а половину выдачи мы не взяли.
            print(
                f"серии {plan.want} нет в раздачах: {len(skipped)} "
                f"(«{_cut(skipped[0].raw_name, 60)}»...) - беру ту, где она есть"
            )
        tried: list[str] = []
        verdicts = 0
        exhausted = False
        deadline = time.monotonic() + PICK_BUDGET
        for attempt, number in enumerate(queue, start=1):
            prep = self.start(plan, number)
            following = queue[attempt] if attempt < len(queue) else None
            if following is not None:  # запасной греется, пока ждём этот
                self.start(plan, following)
            self._wait(prep, progress)
            trouble = self._trouble(
                prep, pinned=args.pinned, warn_mbit=plan.warn_mbit, recode=plan.recode_at > 0
            )
            if not trouble:
                progress.phase("")
                prep = self._honest(plan, prep, queue, args, progress)
                # Молчаливых подмен нет ни в одну сторону: и «ресивер может не взять», и
                # «перекодирую целиком» - это решение показа, и человек его слышит.
                if prep.found.recoded_whole and plan.recode_at > 0:
                    print(recode_note(prep.found.video or ""))
                elif warning := prep.found.video_warning:
                    print(warning)
                return prep
            tried.append(f"{number} - {trouble}")
            trace.emit("select", "drop", release=number, why=trouble)
            if not prep.error and prep.media is not None:  # ffprobe прочитал и осудил
                verdicts += 1
            self._forget(prep)
            progress.phase("")
            goes_on = following is not None and verdicts < MAX_TRIES and time.monotonic() < deadline
            tail = f" - беру {following}" if goes_on else ""
            print(f"релиз {number} не годится ({trouble}){tail}")
            if not goes_on:
                # Дошли до конца очереди, а не встали по бюджету/попыткам: следующего нет.
                exhausted = following is None
                break
        shown = "; ".join(tried[:MAX_TRIES])
        more = f" и ещё {len(tried) - MAX_TRIES}" if len(tried) > MAX_TRIES else ""
        offer = kin_line(plan.kin)
        tail = f"\n{offer}" if offer else ""
        if verdicts == 0 and exhausted and tried:
            # «Не нашли» и «нашли, но рой мёртв» - разные отказы. Очередь пройдена до конца, и
            # ни один релиз не дошёл до приговора: ffprobe не прочитал ни одного, потому что не
            # приехали ни метаданные по DHT, ни поток. Раздачи есть и по именам годны - мёртв
            # рой, а не выбор. Врать «годного релиза нет» тут нельзя: выбирать руками не из
            # чего, пиров нет ни у кого. Если же встали по бюджету (очередь не пройдена), ниже
            # могли остаться живые - тогда прежняя строка, она про «ещё есть что пробовать».
            raise NotFoundError(
                f"раздач нашлось {len(tried)}, но рой у них мёртв - пиров нет, "
                f"показывать нечего ({shown}{more})" + tail
            )
        raise NotFoundError(
            f"годного релиза нет ({shown}{more}): выбери руками - "
            "cast releases <запрос>, потом cast <запрос> --release N" + tail
        )

    def _wait(self, prep: _Prep, progress: Progress) -> None:
        """Дождаться подготовки, показывая фазу и бегущее время."""
        deadline = prep.started + self.meta_budget + self.probe_budget + 5.0
        while not prep.ready.wait(0.2):
            progress.phase(prep.phase)
            if time.monotonic() > deadline:  # поток сам не уложился - не ждём вечно
                prep.error = prep.error or f"фаза «{prep.phase}» не уложилась в бюджет"
                return

    def _peek(self, prep: _Prep, progress: Progress, deadline: float, phase: str) -> bool:
        """Заглянуть в подготовку с коротким сроком: успела — ``True``, нет — ``False``.

        Отличие от :meth:`_wait` не в сроке, а в последствиях: этот срок наш, а не
        релиза, и просроченному прогреву :attr:`_Prep.error` не ставится. Иначе
        подглядывание за соседом молча делало бы его негодным.
        """
        while not prep.ready.wait(0.2):
            progress.phase(phase)
            if time.monotonic() > deadline:
                return False
        return True

    def _honest(
        self, plan: _Plan, chosen: _Prep, queue: list[int], args: Args, progress: Progress
    ) -> _Prep:
        """Подтверждённое разрешение против обещанного: 574p вместо 1080p — не мелочь.

        Верх отбора — самый обсиженный годный кандидат, и это правило остаётся.
        Но обсиженность считается **среди честных**: если ffprobe уже прочитан и говорит,
        что внутри верха не HD, а рядом в очереди стоит живой релиз, который обещает
        1080p, — стоит спросить у ffprobe и его. Живой случай, ради которого это
        написано: «Моана 2», верх ``WEB-DL-AVC`` 3.14 ГБ / 140 сидов оказался 1150×574,
        а вторым лежит настоящий 1080p 13.3 ГБ со 121 сидом.

        Платим за проверку немного: запасной греется с той же секунды, что и верх
        (:meth:`resolve` поднимает следующего сразу), поэтому ждём не прогрев, а разницу
        двух ffprobe, и не дольше :data:`HONEST_BUDGET`.

        Молчаливых подмен нет в обе стороны: и подмена, и отказ от неё печатают строку.
        ``--release N`` и ``--file N`` не трогаем вовсе — там человек выбрал сам.
        """
        if args.release is not None or args.pinned:
            return chosen
        short = understated(chosen.release, chosen.found)
        if not short:
            return chosen
        # Очередь целиком тут не спрашивается: каждый вопрос - это ещё одна раздача в
        # TorrServer, то есть кэш и полоса роя у того, кого мы и так вот-вот покажем.
        rest = [
            n
            for n in queue
            if n != chosen.number and promises_more(plan.ranked[n - 1], chosen.found)
        ][:MAX_TRIES]
        deadline = time.monotonic() + HONEST_BUDGET
        for number in rest:
            alt = self.start(plan, number)
            phase = f"релиз {chosen.number} {short} - смотрю {number}"
            if not self._peek(alt, progress, deadline, phase):
                progress.phase("")
                print(f"релиз {number} не успел ответить - играю {chosen.number} ({short})")
                return chosen
            progress.phase("")
            why = self._trouble(
                alt, pinned=False, warn_mbit=plan.warn_mbit, recode=plan.recode_at > 0
            )
            if why:
                print(f"релиз {number} не годится ({why})")
                continue
            if not honest_shot(alt.release, alt.found) or alt.found.frame <= chosen.found.frame:
                print(f"релиз {number} не лучше ({quality_text(alt.release, alt.found)})")
                continue
            print(f"релиз {chosen.number} {short} - беру {number} (настоящий {alt.found.quality})")
            self._forget(chosen)  # верх больше не нужен: полосу роя доедать ему незачем
            return alt
        print(f"релиз {chosen.number} {short} - честнее рядом нет, играю его")
        return chosen

    def _trouble(
        self, prep: _Prep, pinned: bool, warn_mbit: float = 0.0, recode: bool = False
    ) -> str:
        """Почему релиз не годится; пусто — годится. Названный руками не подменяется.

        Битрейт здесь считается **по прочитанному файлу**, а не по размеру раздачи, и это
        разные числа: у «Моаны 2» прикидка (:func:`bitrate_of`) делит 13.3 ГБ на типовые
        два часа и даёт 14.8 Мбит/с, а внутри — фильм на 1:39:37, то есть честные
        17.8 Мбит/с, на которых Q70D встаёт в ребуфер раз в 30–60 с.
        Прикидка потолка при выборе дефолта такой релиз пропускала и пропускать будет:
        до ffprobe длительности картины не знает никто. Поэтому потолок проверяется ещё
        раз — тем же числом, которое показ печатает пользователю.

        ⚠️ ``warn_mbit`` здесь — это ``bitrate_hard_mbit``, а не потолок декодера:
        тяжёлые куски перекодируются, и «Моана 2» на 19 Мбит/с теперь годится.
        Отбраковывается только то, что перекодированием не спасти.

        ⚠️ Само число берётся из **паспорта** — веса видеодорожки, — а не из размера
        файла (:meth:`torrcast.stream.Media.weight_mbit`). Отбраковка спрашивает
        «сколько придётся перекодировать», а десять озвучек и двенадцать субтитров
        перекодировать не придётся: они на ТВ не уезжают вовсе.

        ⚠️ **HEVC больше не отказ** (``recode``): такой файл перекодируется целиком
        (:data:`torrcast.stream.RECODE_CODECS`), и аниме — жанр, где HEVC бывает вообще
        всем, что нашлось, — теперь играет. Предпочтение H.264 при прочих равных живёт
        не здесь, а в ранжире (:func:`rank_releases` топит hevc ниже всех), то есть
        сплошной перекод достаётся ровно тем релизам, у которых альтернативы нет.
        """
        if prep.error:
            return prep.error
        if prep.media is None or prep.video is None:
            return "поток не прочитан"
        if not pinned and warn_mbit > 0:
            peak = prep.media.weight_mbit(prep.video.size)
            if peak > warn_mbit:
                return f"тяжёлый, ~{peak:.0f} Мбит/с"
        codec = prep.media.video or "h264"
        if pinned or codec == "h264" or (recode and prep.media.recoded_whole):
            return ""
        return codec

    def _forget(self, prep: _Prep) -> None:
        """Убрать раздачу из TorrServer: она либо не подошла, либо больше не нужна."""
        prep.dropped = True
        if prep.torrent_hash:
            self.torrserver.drop(prep.torrent_hash)

    def drop_all(self) -> None:
        """Показа не будет: всё прогретое убирается из TorrServer.

        Выходов мимо :meth:`keep_only` хватает — Ctrl-C на вопросе «Что смотрим?», запуск
        без терминала, «годного релиза нет». Раздачи при этом уже добавлены и тянут кэш в
        RAM до перезапуска TorrServer: ``save_to_db`` у них выключен, но живут они не в
        нашем процессе, и умирают не вместе с ним.
        """
        for prep in self.preps.values():
            self._forget(prep)

    def keep_only(self, chosen: _Prep) -> None:
        """Оставить в TorrServer одну раздачу — ту, которую показываем.

        Прогрев по определению греет лишнее: топ-3 картины франшизы и запасной релиз.
        Всё лишнее обязано исчезнуть до старта показа, иначе оно доедает и кэш в RAM,
        и полосу роя, а показ идёт ровно на них (и tmpfs не должен расти без предела).
        """
        for prep in self.preps.values():
            if prep is not chosen:
                self._forget(prep)

    def _work(self, plan: _Plan, prep: _Prep) -> None:
        """Фоновая подготовка: раздача в TorrServer, метаданные по DHT, ffprobe."""
        try:
            prep.phase = "метаданные (DHT)"
            prep.torrent_hash = self.torrserver.add(prep.release.magnet)
            files = self.torrserver.wait_files(prep.torrent_hash, timeout=self.meta_budget)
            prep.meta = time.monotonic() - prep.started
            mark("метаданные", релиз=prep.number, картина=plan.picture.key)
            prep.video = self.choose(plan, prep.release, files)
            prep.phase = "дорожки"
            began = time.monotonic()
            source = self.torrserver.stream_url(prep.torrent_hash, prep.want.index)
            # Всё, что показ прочитает из роя первым, читается здесь и сейчас: карта
            # опорных кадров (без неё нет сетки) и начало файла (его читает ffmpeg). Это
            # самая ранняя секунда, когда известен файл, - то есть параллельно и ffprobe,
            # и вопросам человека. Показ потом либо берёт готовое, либо
            # дожидается этого же чтения, а не начинает своё вторым потоком.
            warm_file(source, alive=lambda: not prep.dropped, name=prep.want.name)
            prep.media = probe(
                source, timeout=self.probe_budget, alive=swarm_pulse(source, SWARM_GRACE)
            )
            prep.read = time.monotonic() - began
            mark("ffprobe", релиз=prep.number, картина=plan.picture.key)
            prep.phase = "готово"
        except TorrcastError as exc:
            prep.error = str(exc)
            prep.phase = "сбой"
        finally:
            prep.ready.set()
            if prep.dropped:  # пока грелись, показ ушёл к другому релизу
                self._forget(prep)


def _default_file(plan: _Plan, release: Release, files: list[TorrFile]) -> TorrFile:
    """Фильму — самый крупный видеофайл, сериалу — файл нужной серии."""
    return plan.series.choose(release, files) if plan.series else pick_video_file(files)


def _file_picker(args: Args) -> Callable[[_Plan, Release, list[TorrFile]], TorrFile]:
    """``--file N`` — отладочная ручка: взять N-й видеофайл раздачи."""
    if args.file is None:
        return _default_file

    def chosen(plan: _Plan, release: Release, files: list[TorrFile]) -> TorrFile:
        ordered = sorted(files, key=lambda f: f.index)
        videos = [f for f in ordered if f.name.lower().endswith(VIDEO_EXT)]
        if not 1 <= (args.file or 0) <= len(videos):
            raise NotFoundError(f"видеофайлов в раздаче {len(videos)}, номера {args.file} нет")
        return videos[(args.file or 1) - 1]

    return chosen


@dataclass(slots=True)
class _Resume:
    """Прогрев под вопросом «Продолжить?» — то же, что прогрев под меню, но для позиции.

    Продолжение с середины упирается не в поиск (его тут нет вовсе), а в рой: показу
    нужны заголовок файла и то место, где лежит сохранённая позиция, а холодная раздача
    отдаёт новое место секундами. Единственная свободная секунда на этом пути — та, пока
    человек читает вопрос, и она тут и тратится.

    Смещение позиции в байтах берётся из карты опорных кадров
    (:meth:`torrcast.stream.FilmKeys.byte_at`) — той же самой, по которой строится сетка.
    Пропорция «доля фильма от размера файла» сюда не годится: битрейт по фильму гуляет
    вдвое, и промах в проценте — это десятки мегабайт, то есть прогрев не того места.
    """

    torrserver: TorrServer
    entry: Entry
    source: str = ""
    cancelled: bool = False

    def start(self) -> None:
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self) -> None:
        with contextlib.suppress(TorrcastError):
            torrent_hash = self.torrserver.add(self.entry.magnet)
            files = self.torrserver.wait_files(torrent_hash)
            self.source = self.torrserver.stream_url(torrent_hash, self.entry.file_idx)
            # Имя файла - подсказка о контейнере для грелки головы: карта, снятая прошлой
            # версией, лежит в кэше без него (:func:`torrcast.stream.container_of`).
            name = next((f.name for f in files if f.index == self.entry.file_idx), "")
            warm_file(self.source, at=self.entry.pos, alive=lambda: not self.cancelled, name=name)

    def enough(self) -> None:
        """Ответ получен — прогрев прекращается, дальше те же байты читает сам показ.

        ⚠️ Это не мелочь и не гигиена, а замер. Прогрев, доигрывающий после Enter'а, —
        это **второй** читатель того же места через TorrServer, и он отбирает у показа
        ровно то, ради чего затевался: в замере пробный прогон вырос с 0.56
        до 1.92 с, а готовность LOAD — с 3.5 до 4.8 с. Смысл прогрева весь в секундах
        ДО ответа; после ответа лучший потребитель полосы — ffmpeg.

        «Сначала» отменяет прогрев по той же причине, только резче: середина фильма
        больше не нужна вовсе.
        """
        self.cancelled = True


def _resume(config: Config, key: str, entry: Entry, clock: _Clock, dry: bool = False) -> int:
    """Возобновление: один вопрос и сразу показ. Релиз, файл и дорожка берутся из
    состояния — ни поиска, ни меню, поэтому старт укладывается в 5–15 с.

    Пока задаётся вопрос, раздача уже поднята в TorrServer, а рой прогрет по месту
    сохранённой позиции (:class:`_Resume`): к Enter'у критический путь чаще всего пуст.
    """
    warm = _Resume(TorrServer(config.torrserver_url), entry)
    warm.start()
    question = f"«{entry.title}» остановились на {_hms(entry.pos)}. Продолжить? [Да/сначала]"
    answer = ask_line(question)
    warm.enough()
    if answer[:1] in {"с", "s", "н", "n"}:  # «сначала» / «с начала» / «нет»
        entry.pos = 0.0
    mark("ответы")  # ноль секундомера: Enter после последнего вопроса
    return _launch(config, key, entry, _about(entry), clock, dry)


def _launch(
    config: Config, key: str, entry: Entry, about: str, clock: _Clock, dry: bool = False
) -> int:
    """Показ уезжает в transient-юнит: ``cast`` завершился — показ продолжается."""
    if dry:
        print(f"(--dry) {about} - каста нет")
        return EXIT_OK
    # Сначала гасим прошлый показ и только потом пишем свою запись: умирающий юнит по
    # SIGTERM дописывает СВОЮ позицию, и записанный раньше прыжок на s1e5 он бы затёр.
    stop_play_unit()
    state = State.load()
    state.put(key, entry)
    state.save()
    forget_playing(Path(config.hls_dir))  # флажок прошлого показа нам не доказательство
    start_play_unit(key)
    mark("юнит")
    with Progress() as progress:
        _await_playing(config, progress)
    print(f"играю {about} - на ТВ   (старт {clock.total:.0f} с)")
    return EXIT_OK


def _await_playing(config: Config, progress: Progress, timeout: float = START_BUDGET) -> None:
    """Дождаться **картинки на экране**, а не «упаковка пошла».

    Две разные вещи, которые легко счесть одной: первый сегмент в tmpfs — это упаковка, а
    картинка — это приёмник, ответивший ``PLAYING``. Спросить приёмник отсюда нельзя:
    сендер к нему должен быть ровно один, и он живёт в юните (см. :mod:`torrcast.cast`).
    Поэтому юнит кладёт флажок (:func:`mark_playing`), а CLI его ждёт — и печатает
    «старт NN с» ровно в тот момент, когда на экране появилось изображение.
    """
    out = Path(config.hls_dir)
    flag = playing_flag(out)
    deadline = time.monotonic() + timeout
    packed = False
    while time.monotonic() < deadline:
        if flag.exists():
            mark("картинка")
            progress.phase("")
            return
        if not packed:
            with contextlib.suppress(OSError):
                packed = any(out.glob("v*.ts"))
            if packed:
                mark("первый сегмент")
        progress.phase("жду телевизор" if packed else "упаковка")
        if not unit_active():
            progress.phase("")
            raise InfraError(f"показ не запустился: {unit_why()}")
        time.sleep(0.2)
    progress.phase("")
    stop_play_unit()
    raise InfraError(f"показ не начался за {timeout:.0f} с - {unit_why()}")


def _recoder(
    source: str,
    audio: int,
    grid: Grid,
    spare: Path,
    config: Config,
    video_mbit: float = 0.0,
) -> Recoder | None:
    """Кодировщик тяжёлых кусков или ``None``, если он не нужен и не может помочь.

    Профиль тяжести считается из уже снятой карты опорных кадров: байты и секунды каждого
    сегмента известны до упаковки, и это ноль запросов к рою. Отказ бывает честный —
    выключено настройкой, сетка не по кадрам (тогда границы не совпадут с картой), карта
    снята прошлой версией и смещений не несёт, — и о нём говорится вслух.
    """
    from torrcast.recode import Encode, Recoder, Weights
    from torrcast.stream import AUDIO_MBIT, TS_OVERHEAD, film_keys

    if not config.recode:
        return None
    if not grid.on_keys:
        print("сетка не по опорным кадрам - тяжёлые куски перекодировать не берусь", flush=True)
        return None
    try:
        keys = film_keys(source)
    except InfraError as exc:
        print(f"профиль тяжести не снят ({why(exc)}) - играю как есть", flush=True)
        return None
    # Сколько уедет на ТВ: видеодорожка идёт копией, звук всегда AAC, сверху оверхед
    # mpegts. Паспорт молчит (mp4 без тегов) - поправка наберётся по факту, как раньше.
    delivered = (video_mbit + AUDIO_MBIT) * TS_OVERHEAD if video_mbit > 0 else 0.0
    weights = Weights.of(keys, grid, delivered=delivered)
    if weights is None:
        print("карта без смещений - профиль тяжести не построить, играю как есть", flush=True)
        return None
    print(
        f"профиль тяжести: контейнер {weights.container:.1f} Мбит/с, "
        + (
            f"на ТВ уедет {delivered:.1f} (видео {video_mbit:.1f} по паспорту)"
            if delivered > 0
            else "веса видеодорожки в паспорте нет - поправку наберу по факту"
        ),
        flush=True,
    )
    return Recoder(
        source=source,
        audio=audio,
        grid=grid,
        spare=spare,
        weights=weights,
        threshold=config.recode_at_mbit,
        encode=Encode(preset=config.recode_preset, mbit=config.recode_mbit),
        ahead=config.recode_ahead,
        cache_mb=config.recode_cache_mb,
        head_wait=config.recode_head_wait,
        log=lambda text: print(text, flush=True),
    )


def _encode_all(config: Config, codec: str, video_mbit: float = 0.0) -> Encode | None:
    """Чем перекодировать ВЕСЬ файл или ``None`` — если видео уезжает копией, как всегда.

    Решение файл-уровневое и принимается один раз, по паспорту ffprobe: приёмник либо
    декодирует кодек, либо нет (:data:`torrcast.stream.RECODE_CODECS`), и середины тут не
    бывает. Посегментное решение по весу и битрейту на таком файле давало **смешанный**
    поток H.264 и HEVC — на живом Q70D это 24 с картинки и вечная петля «залип →
    перезагрузка»: ровно на границе первого не перекодированного куска.

    Битрейт — не потолок, а **цель**, и она считается от источника. ``recode_mbit``
    остаётся потолком, но брать его всегда нельзя: 🔴 замер на живом Q70D (TC-29,
    «Bocchi the Rock» — 1.3 Мбит/с HEVC) показал, что перекод «в 9 Мбит/с» раздувает
    лёгкое аниме в семь раз, кладёт в сегменты 18.3 и 21.4 МБ при потолке 16 и тратит
    процессор на биты, которых в источнике нет. Отсюда :data:`FULL_GAIN` — во сколько
    раз H.264 тем же ``ultrafast`` (без CABAC и почти без анализа) дороже HEVC при
    сравнимой картинке, — и :data:`FULL_FLOOR`, ниже которого 1080p разваливается.
    """
    if not config.recode or (codec or "") not in RECODE_CODECS:
        return None
    want = config.recode_mbit
    if video_mbit > 0:
        want = min(want, max(FULL_FLOOR, video_mbit * FULL_GAIN))
    return Encode(preset=FULL_PRESET, mbit=want)


def _layout(
    config: Config, source: str, length: float, codec: str, video_mbit: float, say: Any = None
) -> tuple[Grid, Encode | None]:
    """Сетка сегментов и решение «перекодировать файл целиком» - одной парой.

    Отдельной функцией потому, что считать это приходится дважды и обязательно
    одинаково: один раз показу (:func:`_play`), другой - прогреву следующей серии впрок
    (:func:`_next_warmer`). Разойдись они хоть в одном знаке после запятой - прогретое
    легло бы под другим ключом (:func:`torrcast.warm.warm_key`), и показ, ради которого
    всё грелось, своего же прогретого не нашёл бы.

    Порядок внутри тоже не случаен: сплошной перекод решается ДО сетки, потому что от
    битрейта перекода зависит вес каждого куска, а значит и то, где сетка ставит границы.
    """
    from torrcast.stream import AUDIO_MBIT, TS_OVERHEAD, grid_for

    whole = _encode_all(config, codec, video_mbit)
    grid = grid_for(
        source,
        length,
        config.hls_segment,
        config.hls_keyframes,
        say=say,
        delivered_mbit=(video_mbit + AUDIO_MBIT) * TS_OVERHEAD if video_mbit > 0 else 0.0,
        ceiling_mbit=config.recode_mbit if config.recode else 0.0,
        # Сплошной перекод: вес куска задаём мы сами, карта источника тут не судья.
        fixed_mbit=(whole.mbit + AUDIO_MBIT) * TS_OVERHEAD if whole is not None else 0.0,
    )
    return grid, whole


def _next_warmer(config: Config, torrserver: Any, torrent_hash: str, entry: Entry) -> Warmer | None:
    """Прогрев СЛЕДУЮЩЕЙ серии - тем же механизмом, каким грелась текущая.

    Зовётся лениво и ровно один раз: когда текущая серия уже лежит на диске целиком и
    больше не нуждается ни в одном байте раздачи (:meth:`torrcast.warm.Warmer._chain`).
    Раньше этого момента следующая серия не имеет права ни на полосу, ни на процессор.

    ⚠️ Побочный смысл этой сборки не меньше самого прогрева. Автопереход на следующую
    серию (:func:`_cmd_worker`) начинается с двух вопросов к раздаче: паспорт файла
    (:func:`probe` - длительность для порога 95 %) и карта опорных кадров
    (:func:`torrcast.stream.film_keys` - сетка и манифест). Посреди обрыва связи спросить
    их не у кого, и показ, у которого следующая серия ЛЕЖИТ на диске, всё равно уткнулся
    бы в мёртвую раздачу. Здесь оба вопроса задаются заранее и оба ложатся в кэш на диск.

    ``None`` - греть нечего: фильм, последняя серия раздачи или запись без списка серий.
    """
    from torrcast.recode import RECODE_DIR
    from torrcast.stream import hls_dir, probe

    following = entry.advance()
    if following.done or not following.label:
        return None
    source = torrserver.stream_url(torrent_hash, following.file_idx)
    media = probe(source, timeout=WORKER_DUR)
    video_mbit = max(0.0, media.video_bps / 1e6)
    grid, whole = _layout(config, source, media.duration, media.video or "", video_mbit)
    recoder = (
        None
        if whole is not None
        else _recoder(
            source,
            following.audio,
            grid,
            hls_dir(config.hls_dir) / RECODE_DIR,
            config,
            video_mbit=video_mbit,
        )
    )
    title = " ".join(filter(None, (following.title, following.label)))
    return _warmer(
        config,
        source,
        following.audio,
        grid,
        0.0,
        title,
        whole=whole,
        recoder=recoder,
    )


def _warmer(
    config: Config,
    source: str,
    audio: int,
    grid: Grid,
    start: float,
    title: str,
    whole: Any = None,
    recoder: Any = None,
    follow: Any = None,
) -> Warmer | None:
    """Фоновый прогрев всего фильма на диск или ``None``, если он выключен.

    Чем кодировать прогретое — решается здесь и один раз на показ, потому что стык двух
    прогонов ffmpeg стоит показу дыры в звуке (докстринг :mod:`torrcast.warm`):

    * кодек, который приёмник не декодирует, — тем же сплошным перекодом, что и живая
      упаковка (``whole``): иначе на диске лежал бы HEVC, который ТВ не возьмёт;
    * фильм с тяжёлыми кусками (жив кодировщик) — целиком в потолок ``recode_mbit``.
      Наружу такой фильм и так уезжает перекодированным в тяжёлых местах, а держать
      прогрев «копия там, перекод тут» нельзя: каждый переход между режимами — это
      новый прогон, то есть стык звука посреди фильма;
    * всё остальное — копией, как играет живая упаковка.
    """
    if not config.warm:
        return None
    encode = whole
    if encode is None and recoder is not None and recoder.targets:
        encode = Encode(preset=FULL_PRESET, mbit=config.recode_mbit)
    vault = Vault(
        root=warm_root(config.warm_dir),
        key=warm_key(source, audio, grid, encode),
        budget=int(config.warm_budget_gb * 1e9),
        title=title,
    )
    return Warmer(
        source=source,
        audio=audio,
        grid=grid,
        vault=vault,
        encode=encode,
        began_at=grid.slot_at(start),
        rate=config.warm_rate,
        follow=follow,
        log=lambda text: print(text, flush=True),
    )


def _play(
    config: Config,
    source: str,
    audio: int,
    about: str,
    clock: _Clock,
    watch: Watch | None = None,
    duration: float = 0.0,
    receiver: Receiver | None = None,
    codec: str = "",
    follow: Any = None,
) -> int:
    """Упаковка → раздача по http на голом IP → приёмник. Своих демонов нет: и ffmpeg,
    и раздача живут ровно на время показа и гасятся вместе с ним, что бы ни случилось.

    Упаковка за показ перезапускается столько раз, сколько человек перемотал: манифест
    обещает приёмнику весь фильм, а :class:`Feed` пакует то место, которое он попросил.
    Раздача, приёмник и LOAD при этом одни на весь показ.

    ``follow`` - чем прогреву заняться, когда эта серия ляжет на диск целиком
    (:attr:`torrcast.warm.Warmer.follow`); у фильма его нет и быть не может.
    """
    from torrcast.recode import RECODE_DIR
    from torrcast.stream import hls_base, hls_dir

    out = hls_dir(config.hls_dir)
    start = watch.entry.pos if watch else 0.0
    length = watch.entry.dur if watch else duration
    tls = config.transport == "https"
    video_mbit = max(0.0, watch.entry.vbps) if watch else 0.0
    # Сетка сегментов снимается с самого файла и дальше не меняется: она же в манифесте,
    # она же в команде ffmpeg. Всё, что показ говорит о времени, считается по ней.
    #
    # Сетке нужен не только шаг, но и вес. Сегмент тяжелее ~19 МБ приёмник не
    # доигрывает, а выбрасывает буфер и качает его заново, поэтому граница ставится с
    # оглядкой на предсказанный вес куска - а он зависит и от паспорта (что уедет на ТВ),
    # и от того, перекодируем ли мы тяжёлое (тогда кусок не тяжелее ``recode_mbit``).
    # Кодек, который приёмник не декодирует, - это решение на весь показ, а не на кусок:
    # перекодирует сама упаковка, одним прогоном, и кодировщик тяжёлых кусков не нужен -
    # перекодировать поверх перекода нечего. Решается это ДО сетки: от битрейта перекода
    # зависит вес каждого куска, а значит и то, где сетка поставит границы.
    grid, whole = _layout(
        config, source, length, codec, video_mbit, say=lambda text: print(text, flush=True)
    )
    mark("сетка", сегментов=grid.count, покадрам=grid.on_keys)
    if whole is not None:
        print(recode_note(codec), flush=True)
        mark("сплошной перекод", кодек=codec, пресет=whole.preset, мбит=round(whole.mbit, 2))
    # Профиль тяжести всего фильма известен со старта - он считается из уже снятой
    # карты опорных кадров и не стоит ни одного запроса к рою. Тяжёлые куски кодировщик
    # начнёт перекодировать сразу, пока играет остальное.
    recoder = (
        None
        if whole is not None
        else _recoder(
            source,
            audio,
            grid,
            out / RECODE_DIR,
            config,
            video_mbit=video_mbit,
        )
    )
    # Прогрев поднимается ПОСЛЕ старта показа (ниже), а собирается здесь: ему нужны и
    # сетка, и решение о перекодировании - те же, что у живой упаковки.
    warmer = _warmer(
        config, source, audio, grid, start, about, whole=whole, recoder=recoder, follow=follow
    )
    feed = Feed(
        source=source,
        audio=audio,
        out=out,
        grid=grid,
        readrate=config.hls_readrate,
        burst=config.hls_burst,
        keep=config.hls_keep,
        log=lambda text: print(text, flush=True),
        recoder=recoder,
        encode=whole,
        vault=None if warmer is None else warmer.vault,
    )
    server = HlsServer(
        out, config.hls_cert, config.hls_key, port=config.hls_port, tls=tls, feed=feed
    )
    # Серт приёмнику нужен только затем, чтобы проверить нашу раздачу: по http проверять
    # нечего, и mock не должен делать вид, что что-то проверил. Готовый приёмник приходит
    # с сериалом: он один на весь юнит (см. :func:`_cmd_worker`).
    if receiver is None:
        receiver = make_receiver(config.receiver, config.tv or "", config.hls_cert if tls else "")
    url = f"{hls_base(config)}/index.m3u8"
    try:
        server.start()
        mark("раздача")
        # Упаковку начинаем сами, не дожидаясь первого запроса: ресиверу нужен готовый
        # кусок сразу, иначе LOAD упирается в ожидание ffmpeg и старт растёт на глазах.
        if recoder is not None:
            recoder.played = start
            recoder.start()
        feed.restart(grid.slot_at(start))
        mark("упаковка пошла")
        receiver.play(url, about, at=start)
        mark("LOAD взят")
        print(f"играю {about} - на ТВ   (старт {clock.total:.0f} с)", flush=True)
        # ⚠️ Прогрев стартует ровно ЗДЕСЬ и ни строкой выше: путь до картинки он не
        # удлиняет ни на секунду - ни своим ffmpeg, ни чтением каталога. Всё, что он
        # делает, происходит уже при играющем показе и на остатке процессора.
        if warmer is not None:
            warmer.start()
        _hold(receiver, feed, watch, warmer)
    finally:
        # Позиция фиксируется при любом исходе, включая SIGTERM, и делается это ПЕРВЫМ
        # делом: показ, доигранный до конца файла, отмечает «досмотрено» ровно здесь, а
        # приёмнику ниже нужно уже готовое состояние - по нему он и узнаёт, конец это
        # показа или стык серий.
        if watch is not None:
            watch.flush()
            trace.emit(
                "session",
                "session_end",
                pos=round(watch.entry.pos, 1),
                dur=round(watch.entry.dur, 1),
                watched=bool(watch.done),
            )
        if warmer is not None:
            warmer.stop()
            # Досмотрено (порог 95 %) - прогретое стирается: держать на диске фильм,
            # который уже посмотрели, незачем. Прерванный показ прогретое сохраняет:
            # `cast` завтра продолжит с диска и без сети.
            if watch is not None and watch.done:
                warmer.vault.clear()
                print("досмотрено - прогретое с диска убрал", flush=True)
        # ⚠️ suppress(Exception), а не TorrcastError: pychromecast на полуживом соединении
        # роняет что угодно, а ffmpeg и раздача обязаны погаснуть в любом случае - иначе
        # процесс уходит, а они остаются.
        with contextlib.suppress(Exception):
            # Показ кончился - приложение приёмника закрываем, чтобы ТВ вернулся в
            # исходное состояние: иконка Default Media Receiver иначе висит до своего
            # таймаута простоя и оттягивает автовыключение.
            # Исключение ровно одно - стык серий: следующая серия грузится в то же
            # приложение, и гасить его между ними значит моргать экраном на каждой.
            receiver.stop(quit_app=not _handover(watch))
        feed.stop()
        server.stop()

    report = getattr(receiver, "report", None)
    if report is None:
        return EXIT_OK
    print(report.line())
    # Серию обрывают намеренно на пороге 95 % - хвост упаковки декодеру и не отдавали.
    if not report.ok and not (watch is not None and watch.done):
        raise InfraError("приёмник не досмотрел поток - цифры выше")
    return EXIT_OK


def _handover(watch: Watch | None) -> bool:
    """Правда ли показ передают следующей серии, а не заканчивают.

    Порог 95 % уже записал в состояние следующую серию (:meth:`Watch.flush`), поэтому
    ответ лежит там же, где его читает :func:`_cmd_worker`, — двух разных мнений о конце
    показа быть не должно.
    """
    return watch is not None and watch.done and _following(watch.key) is not None


def _hold(
    receiver: Receiver, feed: Feed, watch: Watch | None = None, warmer: Warmer | None = None
) -> None:
    """Держим показ: опрос приёмника раз в 2 с, упаковка должна быть жива, из RAM уходит
    только пройденное, сторож раз в 10 с пишет позицию.

    Перемотку здесь ловить больше нечем и незачем: приёмник видит весь фильм и на seek
    просто просит сегмент нужного места, а :class:`Feed` пакует оттуда.
    Показу остаётся то, о чём раздача не знает: пауза на пульте и конец показа.

    Придерживать ffmpeg сигналом (SIGSTOP) здесь больше нечем и незачем: темп держит
    сам ffmpeg (``-readrate`` + ``-readrate_initial_burst``), а под паузой процесс
    именно завершается — под SIGSTOP'ом приёмник намертво вис в BUFFERING.
    """
    paused, said, seen = 0.0, 0.0, False
    #: Позиция приёмника с прошлого опроса - от неё считается запас показа. Прошлая, а не
    #: сегодняшняя, потому что запас нужен раньше, чем приходит ответ приёмника, и взять
    #: его больше неоткуда. На решение сторожа это не влияет: нудж срабатывает только
    #: после :attr:`STALL_SECONDS` неподвижности, то есть когда прошлая позиция и есть
    #: сегодняшняя. А сразу после перемотки, где число ещё старое, позиция изменилась -
    #: и счётчик подвиса обнулён.
    last = 0.0
    show_trace = bool(os.environ.get(TRACE_ENV))
    buffering = was_offline = False
    while True:
        _ctl(receiver)
        if trouble := feed.trouble():
            # Убитый сигналом ffmpeg ничего сказать не успевает - не выдумываем за него.
            raise InfraError(f"упаковка оборвалась: {trouble}")
        try:
            # Запас упаковки идёт приёмнику: неподвижный BUFFERING при готовых сегментах
            # впереди - это зависание, а при пустых - законное ожидание нас.
            position = receiver.position(feed.front(last))
        except InfraError:  # приёмник позицию не отдаёт - показу остаётся только ждать
            time.sleep(2.0)
            continue
        last = position.pos
        if not seen and position.state == "PLAYING":
            # Картинка на экране - теперь CLI имеет право сказать «старт NN с».
            seen = True
            mark_playing(feed.out)
        # Ребуфер - только вход в BUFFERING, а не каждый опрос: иначе счётчик считал бы
        # секунды подвиса, а не сами подвисы. Сеть - на переходе в offline и обратно.
        if position.state == "BUFFERING" and not buffering:
            trace.emit("play", "buffering", pos=round(position.pos, 1))
        buffering = position.state == "BUFFERING"
        if bool(feed.offline) != was_offline:
            was_offline = bool(feed.offline)
            if was_offline:
                trace.emit("play", "offline", why=str(feed.offline))
        if show_trace:
            front = feed.front(position.pos)
            print(
                f"запас: показ {position.pos:.0f} · упаковано {front:.0f} · "
                f"впереди {front - position.pos:.0f} с · {feed.weight() / 1e6:.0f} МБ · "
                f"расхождение с манифестом {feed.drift():.3f} с · {position.state}",
                flush=True,
            )
        if warmer is not None:
            # Приоритет живого окна держится ровно здесь: прогрев видит тот же запас, что
            # и сторож приёмника, и на просевшем замирает (:meth:`torrcast.warm.Warmer._throttle`).
            warmer.feed(feed.front(position.pos) - position.pos)
            if warmer.done and feed.rest():
                print("прогрето целиком - живую упаковку гашу, показ идёт с диска", flush=True)
        if time.monotonic() - said >= SAY_SECONDS:
            # Что видит приёмник, тем и отчитываемся: длительность и позиция - это ровно
            # ``duration`` и ``current_time`` из MEDIA_STATUS, снятые владеющим сендером.
            # Другого доказательства «на ТВ есть таймлайн» у нас нет.
            said = time.monotonic()
            print(
                f"экран: {_hms(position.pos)} из {_hms(position.dur)} · {position.state}",
                flush=True,
            )
            if warmer is not None:
                print(warmer.line(), flush=True)
            if feed.offline:
                # Обрыв длиннее прогретого не имеет права быть молчаливой смертью: показ
                # говорит, докуда он обеспечен, и продолжает пробовать сеть.
                print(
                    f"сети нет ({feed.offline}) - показ обеспечен до "
                    f"{_hms(feed.front(position.pos))}",
                    flush=True,
                )
        if watch is not None:
            # Прогрев виден снаружи только через состояние: живой показ из другого
            # процесса не спросишь (:attr:`torrcast.state.Entry.warm`).
            if warmer is not None:
                watch.entry.warm = warmer.warmed
            watch.see(position.pos)
            if watch.done and watch.entry.serial:
                return  # серия досмотрена - освобождаем показ под следующую
        if position.state == "PAUSED":
            paused = paused or time.monotonic()
            if time.monotonic() - paused > PAUSE_LIMIT:
                return  # пауза длиной с вечер - показ окончен, юнит гасим
            if time.monotonic() - paused > PAUSE_SECONDS and not feed.halted():
                print("пауза на пульте - упаковку гашу", flush=True)
                feed.halt()  # вернутся к показу - раздача сама начнёт паковать заново
        elif not position.playing:
            return
        else:
            paused = 0.0
            if feed.recoder is not None:
                feed.recoder.played = position.pos
            feed.prune(position.pos)
        time.sleep(2.0)


@runtime_checkable
class _Steerable(Protocol):
    """Приёмник, которым можно управлять как с пульта (:data:`CTL_ENV`)."""

    def seek(self, pos: float) -> None: ...

    def pause(self) -> None: ...

    def resume(self) -> None: ...


def _ctl(receiver: Receiver) -> None:
    """Исполнить команду диагностического пульта, если она положена (:data:`CTL_ENV`).

    Файл съедается до исполнения: команда одноразовая, и повторить её на следующем опросе
    нельзя даже при осечке приёмника — иначе одна опечатка мотала бы фильм вечно.
    """
    name = os.environ.get(CTL_ENV)
    if not name or not isinstance(receiver, _Steerable):
        return
    path = Path(name)
    try:
        line = path.read_text("utf-8").strip()
    except OSError:
        return
    path.unlink(missing_ok=True)
    if not line:
        return
    word, _, rest = line.partition(" ")
    print(f"пульт: {line}", flush=True)
    with contextlib.suppress(Exception):
        if word == "seek":
            receiver.seek(float(rest))
        elif word == "pause":
            receiver.pause()
        elif word == "play":
            receiver.resume()


def liveliness(plan: _Plan) -> int:
    """Насколько картина живая — сиды у той раздачи, которая реально поедет на ТВ.

    Мерок было три, и две отброшены на живой выдаче:

    * сумма сидов по всем релизам — вытягивает картину числом раздач, а не их
      качеством: у «Матрицы» 1999 сорок релизов против одиннадцати у «Воскрешения»,
      и сумма выбрала бы первую даже с мёртвыми DVD-рипами в хвосте;
    * сиды :attr:`~torrcast.parse.Picture.best_release` — не знают ни про потолок
      битрейта, ни про образы дисков, ни про старьё, а это и есть отбор.

    Осталось честное: берём верх :func:`rank_releases` — то, что Enter и запустит, —
    и считаем его сиды. Годным он обязан быть по :func:`is_candidate`: негодный верх
    (у «Тачек» 2006 это 41-гигабайтный 4K-ремукс на 49.9 Мбит/с, выше потолка
    декодера) означает, что играть у картины нечего, и вес у неё ноль. Заодно сюда
    сам собой затекает :func:`is_dated`: обсиженный .avi больше не тянет картину
    наверх, потому что верхом он уже не бывает.

    Ворота спрашиваются те же, что у самого плана (:attr:`_Plan.loose`), и это не
    мелочь: пока они спрашивались строго, аниме с молчаливыми именами весило ноль
    целиком — у «наруто» дефолтом меню вместо сериала на 91 сид вставал полнометражный
    «Ниндзя в стране снега» на два.
    """
    top = plan.ranked[0] if plan.ranked else None
    if top is None or not is_candidate(top, plan.runtime, plan.warn_mbit, plan.loose):
        return 0
    return top.seeders


def liveliest(plans: list[_Plan]) -> int:
    """Номер (с единицы) самой живой картины — он же дефолт меню и первый на прогрев.

    Список остаётся хронологическим, меняется только цифра в скобках:
    «моана» печатает четыре картины и предлагает вторую, а не немую документалку
    1926 года. Равный вес — берём раннюю: при ничьей хронология и есть ответ.
    """
    return max(range(1, len(plans) + 1), key=lambda n: (liveliness(plans[n - 1]), -n))


def first_alive(plans: list[_Plan]) -> int:
    """Номер (с единицы) картины по умолчанию: **первая по хронологии, чей рой жив**.

    Смотреть франшизу начинают с начала, а не с самой обсиженной части: «тачки» — это
    просьба про «Тачки» 2006, даже когда сидов больше у «Тачек 3». Прежний дефолт
    (:func:`liveliest`) на этом и ошибался — печатал `[4]`.

    Мёртвые части при этом пропускаются, иначе Enter снова упирался бы в пустой рой:
    у «моаны» первой в хронологии стоит «Моана: романтика золотого века» 1926 года,
    немая документалка одним VHS-рипом на 5 сидов.

    Живость — доля от самой живой картины франшизы, порог общий с отбором HD
    (:data:`FULL_HD_LIVENESS`). Абсолютное число тут не годится ровно по той же причине,
    что и там: у свежей части лидер набирает сотни сидов, у части 2006 года — десятки,
    и «30 сидов» значило бы в этих двух пулах разное. Замер по живой выдаче:

    * «тачки» — 66 / 0 / 1 / 121 сид; порог 30, первая часть держит 0.55 от лидера и
      обязана выиграть, а мимо проходят «Мультачки» (одни DVD-образы) и «Тачки 2»,
      у которых годным верхом остался 0.4-гигабайтный HDRip «фильм о фильме» на 1 сид;
    * «моана» — 0 / 222 / 121 / 34; порог 55, документалка 1926 года пропускается,
      дефолтом становится «Моана» 2016.

    Живого нет вовсе — отдаём :func:`liveliest`: выбирать всё равно не из чего, но
    цифра в скобках обязана на что-то указывать, а на пустой франшизе это первый пункт.
    """
    best = max((liveliness(plan) for plan in plans), default=0)
    floor = best * FULL_HD_LIVENESS
    alive = [n for n, plan in enumerate(plans, start=1) if liveliness(plan) >= floor]
    return alive[0] if best > 0 and alive else liveliest(plans)


def warm_order(plans: list[_Plan]) -> list[_Plan]:
    """Кого греть под меню и в каком порядке: сначала дефолт, дальше по хронологии.

    Раньше грелись ``plans[:PREWARM]`` — первые ПО ХРОНОЛОГИИ, потому что дефолтом был
    первый пункт. С дефолтом по :func:`first_alive` это разъезжается ровно там, где
    больнее всего: у «моаны» дефолт — вторая картина, а прогрето было бы 1–3. Enter
    попадал бы в непрогретую картину, а готовность LOAD за 0.6–2.7 с держится как раз
    на том, что карта опорных кадров и голова файла легли в кэш ещё под вопросом; без
    прогрева это снова 3–6 с одного только роя.

    Остальные картины греются по хронологии не от лени: список на экране хронологический,
    и человек, который не соглашается с дефолтом, чаще всего тычет в соседний номер.
    """
    default = first_alive(plans)
    return [plans[default - 1]] + [p for n, p in enumerate(plans, start=1) if n != default]


def _pick_plan(plans: list[_Plan], facts: Facts | None = None) -> _Plan:
    """Вопрос «какой фильм франшизы?»; один вариант — без вопроса.

    Дефолт — первая живая картина франшизы (:func:`first_alive`): смотреть начинают
    с начала, а мёртвые части пропускаются. До этого Enter на «моане» запускал «Моану:
    романтику золотого века» 1926 года — немое документальное кино, один VHS-рип, 5
    сидов, — то есть человек, ответивший так, как приглашает строка `[1]`, гарантированно
    не получал ничего.

    К каждой картине печатается справка (:mod:`torrcast.facts`) — рейтинг, хронометраж и
    фраза о том, что это за кино. Её тут не ждут: что успело приехать фоном, то и
    печатается, остальное просто не печатается.

    Без терминала (ssh без pty, cron, чужой скрипт) спрашивать некого, и общее правило —
    не висеть, а брать дефолт. Здесь мы по-прежнему отказываемся — и «дефолт стал умнее»
    ничего не меняет. У озвучки дефолт считается правилами, у «Продолжить?» это
    «продолжить», а тут любой дефолт означает **другой фильм**: разница между «Моаной»
    2016 и «Моаной 2» — это не оттенок, а не тот вечер. Цифра в скобках имеет смысл
    ровно потому, что рядом напечатан список и человек видит, от чего отказывается;
    без терминала видеть его некому. Поэтому отказываемся вслух и подсказываем, как
    назвать картину точно.
    """
    if len(plans) == 1:
        print(menu_lines(plans, facts))
        return plans[0]
    print(menu_lines(plans, facts))
    default = first_alive(plans)
    if not console.stdin_is_tty():
        raise NotFoundError(
            f"подходит картин: {len(plans)}, а терминала нет - вслепую не выбираю; "
            f"назови картину точно (например «{plans[default - 1].picture.title}») "
            "или запусти cast в терминале"
        )
    return plans[ask("Что смотрим?", len(plans), default=default) - 1]


#: Отступ описания в меню: ровно под название, за номером с точкой.
_BLURB_INDENT = " " * 5


def _named(picture: Picture, aside: bool = False) -> str:
    """Название с годом; ``aside`` - картина стоит после нумерованной линейки франшизы.

    Подпись объясняет, почему пункт уехал вниз: номера части у неё нет, и в линейку по
    номерам ей вставать не с чем (:func:`~torrcast.parse.outside_numbering`).
    """
    marks = ", сериал" if picture.kind == "tv" else ""
    if aside:
        marks += ", без номера части"
    return f"{picture.title} ({picture.year or '?'}{marks})"


def menu_lines(plans: list[_Plan], facts: Facts | None = None, width: int = 0) -> str:
    """Список картин со справкой: номер, название с годом, рейтинг и хронометраж — в одну
    строку, описание — под ней, с отступом под номер.

    Формат такой, а не таблицей, ровно из-за узкого терминала: название бывает длинным
    («Тачки: Мультачки. Байки Мэтра»), а описание — тем более, и колонки разъехались бы
    на первой же франшизе. Отдельная строка вместо колонки ещё и читается сверху вниз:
    глаз идёт по номерам, а подробности — под ними.

    Описание переносится по словам и занимает столько строк, сколько нужно фразе (в
    восьмидесяти колонках это две-три). Раньше оно резалось по ширине терминала, и в
    меню оставался огрызок «американский компьютерно-анимационный…»: ни жанра, ни года,
    ни возможности дочитать. Место экономить тут не на чем — вопрос задаётся один раз.

    Справки нет (не приехала, сети нет, картины нет в Википедии) — печатается ровно та
    строка, что печаталась раньше, без пустых разделителей и без «не нашёл».
    """
    columns = width or shutil.get_terminal_size((80, 24)).columns
    aside = outside_numbering([plan.picture for plan in plans])
    rows: list[str] = []
    for number, plan in enumerate(plans, start=1):
        picture = plan.picture
        fact = facts.get(picture.title, picture.year) if facts else Fact()
        head = " · ".join(
            x for x in (_named(picture, picture.key in aside), fact.rating, fact.runtime) if x
        )
        rows.append(f"  {number}. {head}")
        if fact.about:
            rows += textwrap.wrap(
                shorten(fact.about),
                width=max(40, columns - 1),
                initial_indent=_BLURB_INDENT,
                subsequent_indent=_BLURB_INDENT,
                # Дефис - часть слова: «компьютерно-анимационный» рвать по нему незачем.
                break_on_hyphens=False,
            )
    return "\n".join(rows)


def warned(release: Release, runtime: float, warn_mbit: float, recode_at: float = 0.0) -> str:
    """Почему релиз не дефолт: HEVC ресивер может не потянуть, жирный битрейт — тоже.

    Словами, а не значками: ``⚠`` из вывода убран целиком — в терминале он не нёс
    смысла и разъезжался по ширине.

    ⚠️ «Не берём» про HEVC осталось правдой ровно там, где перекодирование выключено:
    иначе такой релиз играет, перекодированный целиком, и таблица обязана говорить то же,
    что и показ (:func:`_encode_all`).
    """
    peak = bitrate_of(release, runtime)
    marks: list[str] = []
    if release.is_hevc:
        marks += ["перекодирую целиком" if recode_at > 0 else "не берём"]
    if peak > warn_mbit:
        marks += ["тяжёлый"]
    elif recode_at > 0 and peak > recode_at:
        # Не брак, а честное предупреждение - тяжёлые куски поедут перекодированными.
        marks += ["перекодируем"]
    return ", ".join(marks)


def quality_text(release: Release, media: Media) -> str:
    """Разрешение, которое реально поедет на ТВ. ffprobe уже прочитан — врать нечем.

    Порядок именно такой: сначала подтверждённая высота кадра, и только если ffprobe её
    не отдал (экзотика, битый заголовок) — заявка из имени. Раньше было наоборот, и
    «Моана 2» печаталась 1080p при 1150×574 внутри: заявка выигрывала у факта, то есть
    ровно та молчаливая подмена, которой быть не должно.
    """
    return media.quality if media.height else (release.quality or "?")


def understated(release: Release, media: Media) -> str:
    """Чем подтверждённое разрешение хуже обещанного; пусто — релиз честен.

    Две половины, и обе взяты с живой выдачи «моаны 2»:

    1. имя называет разрешение, а внутри заметно меньше (:data:`HONEST_RATIO`);
    2. имя не называет ничего, а внутри не HD вовсе (:data:`HD_HEIGHT`) — это и есть
       верхний кандидат «Моаны 2»: ``WEB-DL-AVC`` без единой цифры в заголовке, 3.14 ГБ,
       140 сидов, а на деле 1150×574.

    Возвращает кусок фразы, а не флаг: строка про подмену обязана назвать обе цифры,
    иначе она ничего не объясняет.
    """
    if not media.height:  # ffprobe высоту не отдал - сравнивать не с чем, молчим
        return ""
    if release.height:
        if media.frame < release.height * HONEST_RATIO:
            return f"назван {release.quality}, на деле {media.quality}"
        return ""
    return f"на деле {media.quality}" if media.frame < HD_HEIGHT else ""


def promises_more(release: Release, media: Media) -> bool:
    """Стоит ли вообще смотреть на этот запасной: обещает HD и больше, чем дал верх."""
    return release.height >= HD_HEIGHT and release.height > media.frame


def honest_shot(release: Release, media: Media) -> bool:
    """Запасной подтвердил своё имя: кадр из ffprobe не ниже заявленной ступени. Имя
    молчало — тогда достаточно, чтобы внутри оказался HD.
    """
    if not media.height:
        return False
    if release.height:
        return media.frame >= release.height * HONEST_RATIO
    return media.frame >= HD_HEIGHT


def is_disc(release: Release) -> bool:
    """Образ диска (DVD-Video, BDMV, ISO): цельного файла внутри нет — не дефолт."""
    return bool(_DISC_RE.search(release.raw_name))


def is_candidate(release: Release, runtime: float, warn_mbit: float, loose: bool = False) -> bool:
    """Кандидат в дефолт: первый сорт (:attr:`Release.prime`), не образ диска и в
    пределах потолка декодера. Жирнее потолка — в таблице остаётся с пометкой, но Enter
    его не возьмёт: ресивер на таком битрейте встаёт.

    ``loose`` — ворота открыты (:func:`gate_open`): живых именных кандидатов у картины
    нет, и тогда кандидатом становится ещё и раздача, чьё имя о качестве просто МОЛЧИТ
    (:attr:`Release.quiet`). Судить её будет ffprobe после выбора — механизм отбраковки
    и перехода к следующему уже стоит на пути (:meth:`_Bench.resolve`), и стоит он
    ровно тех же секунд, что и на любом другом релизе.

    Имя, сказавшее о себе правду, послаблением не пользуется ни при каких воротах:
    названный HEVC, MPEG-4 и «480p» остаются снаружи, потому что про них известно, а не
    неизвестно. Образ диска и потолок битрейта тоже не двигаются: там играть нечего и
    там ресивер встаёт, а от открытых ворот это не меняется.

    ⚠️ Не-видео (``kind == "other"``: игры, музыка, книги) послабление не пускает
    никогда, и это не перестраховка. Замер на живой выдаче «one piece»: репак игры
    «One Piece: Pirate Warriors 4 … PC | RePack» несёт 97 сидов и о качестве видео
    молчит по той простой причине, что видео там нет, — при открытых воротах он
    перевешивал настоящий сериал с русским дубляжом и вставал дефолтом меню.
    """
    if is_disc(release) or bitrate_of(release, runtime) > warn_mbit:
        return False
    return release.prime or (loose and release.quiet and release.kind != "other")


def gate_open(
    releases: list[Release], runtime: float, warn_mbit: float, want: Episode | None = None
) -> bool:
    """Пора ли открыть ворота отбора: живого именного кандидата у картины нет.

    Ворота (:attr:`Release.prime`) защищают от мусора и делают это по делу — пока в
    выдаче есть из чего выбирать. У аниме выбирать нечасто есть из чего: имена раздач
    там сплошь без разрешения, кодека и HD-источника, и ворота оставляют картину вообще
    без живых кандидатов. Живой случай, ради которого написано: «Наруто» (2002) — полный
    сериал «[E220 of 220] [RUS(ext), ENG, JAP+Sub] … DVDRip», 157 ГБ, 91 сид, в
    кандидаты не проходит; проходят «[1-5 из 220]» на 3 сида и «[S01E01-08 of 220]» на
    один. Очередь из двух умирающих огрызков — это не защита от мусора, это отсутствие
    показа.

    «Живой» здесь — доля от лидера пула (:data:`GATE_LIVENESS`), как и у
    :func:`is_full_hd`: абсолютное число в пулах разной населённости значит разное.
    Раздачи, у которых нужной серии нет по их же имени, в счёт не идут — они и в
    очередь не попадают.

    Ворота остаются закрытыми и тогда, когда живых нет вовсе (лидер пула на нуле
    сидов): открывать их незачем, показывать всё равно нечего.
    """
    alive = max((r.seeders for r in releases), default=0)
    if alive <= 0:
        return False
    return not any(
        r.seeders >= alive * GATE_LIVENESS
        and is_candidate(r, runtime, warn_mbit)
        and not misses_episode(r, want)
        for r in releases
    )


def sound_step(release: Release, alive: int = 0) -> int:
    """Ступень звука по имени раздачи: 0 — русская дорожка обещана, 1 — не обещана.

    Решение владельца по аниме: субтитров не делаем, а японскую дорожку без перевода
    смотреть нельзя — значит, при прочих равных релиз с русской озвучкой обязан
    обыграть чисто японский, даже если тот сидастее. У аниме дубляж часто лежит
    ОТДЕЛЬНОЙ раздачей (RuTor, Knaben), а не в релизе Nyaa, и по сидам эта раздача
    проигрывает вчистую: у «Боруто» русский «[RUS(int)]» держит 3 сида против 8 у
    «[JAP+Sub]», у «Врат Штейна» — 2 против 3.

    Ступеней ровно две, и это осознанно сжато с трёх. Промежуточная «имя прямо назвало
    чужой звук» (``[Dual Audio]``, ``[JAP+Sub]``) звучит разумно, но на живой выдаче
    покупается зря: у «Steins;Gate» она меняла верх с 397 сидов на 17, у «Chainsaw Man» —
    с 221 на 34, и русского звука ни там, ни там не появлялось. Менять живой рой на
    мёртвый, ничего не выигрывая, — прямая дорога к подгрузам, а гейт показа обратный.
    Поэтому ступень срабатывает ровно тогда, когда в выдаче ЕСТЬ что предпочесть.

    Молчание имени и чужой звук стоят в ней рядом по той же причине, по какой ворота
    отбора не судят молчание (:attr:`Release.quiet`): молчаливая раздача вполне может
    нести русскую дорожку, и узнать это можно только у ffprobe.

    ``alive`` — сиды лидера пула: мёртвый рой выигрышем не бывает ни на каком языке
    (:data:`SOUND_LIVENESS`). Без него ступень поднимала у «Наруто: Ураганные хроники»
    раздачу с НУЛЁМ сидов над играбельной — то есть меняла японский показ на никакой.
    Ноль (умолчание) читается как «пул не назван» и оставляет чистый сигнал имени: так
    ступень зовут таблица релизов и тесты.
    """
    if not release.dubbed:
        return 1
    return 0 if release.seeders >= alive * SOUND_LIVENESS else 1


def is_dated(release: Release, runtime: float) -> bool:
    """Раздача пахнет старьём — до всякого ffprobe, по имени и размеру.

    Три части признака, и они не взаимозаменяемы:

    1. :attr:`Release.dated` — имя признаётся само: XviD/DivX, ``.avi``, DVDRip/VHSRip/
       SATRip/TVRip/CAM.
    2. Имя называет ступень ниже :data:`HD_HEIGHT` — «480p», «576p». Тут спорить не с чем:
       раздача сама говорит, что она не HD, и место ей ниже любого HD. SD играется, только
       если HD в каталоге нет вовсе, — и тогда порядок внутри группы прежний.
    3. Имя не называет РАЗРЕШЕНИЯ, а размер даёт меньше :data:`SD_BITRATE` Мбит/с. Это и
       есть та раздача, ради которой всё затевалось: «Моана 2 … WEB-DL] Dub (MovieDalen)»,
       221 сид, 1.46 ГБ — в заголовке rutracker ни слова про кодек, а внутри
       ``Moana.2.2024.WEB-DLRip.ELEKTRI4KA.avi`` (проверено по самому .torrent). Ни один
       маркер из пункта 1 её не ловит.

       ⚠️ Названный кодек эту часть больше не отключает, и вот почему. Про РАЗРЕШЕНИЕ
       кодек не говорит ничего: ``BDRip-AVC`` — это и честный 1080p на 6 Мбит/с, и рип
       720×304 на 1.7. Пока «назван кодек» означало «имя не молчит», от эвристики
       ускользал целый пласт rutracker-раздач на 1.45–1.47 ГБ: у «Тёмного рыцаря:
       Возрождение легенды» такая стояла верхом с 58 сидами, у «Форреста Гампа» — со 105,
       у «Зелёной мили» — с 64, и рядом в каждой лежал названный 1080p. Ровно они и дали
       SD-фолбэк топа замера. Разрешение в имени эвристику по-прежнему отключает: там имя
       говорит по делу, и спорить с ним — работа ffprobe (:func:`understated`), а не
       прикидки по размеру.

    Почему это в cli, а не свойством релиза рядом с ``dated``: последней части нужна
    длительность картины, а её знает только план (:class:`_Plan`), не парсер. Ровно та
    же причина держит здесь :func:`bitrate_of` и :func:`is_candidate`.

    Сериалу вторая половина считается **на серию**, а не на раздачу: в ней лежит весь
    сезон, и «6 ГБ» это не битрейт фильма, а восемь серий. Делит их :func:`bitrate_of`
    по счёту серий из имени (``[S01E01-08 of 220]`` → восемь). Раньше здесь стоял
    отказ «сериалу не считаем вовсе», и подтверждённый .avi «Легенды об Аанге» 2024
    года эвристика не понижала — ловил его только ffprobe, то есть 2-5 секунд живого
    старта на раздачу, которую всё равно выбросят.

    ⚠️ Аниме (:attr:`~torrcast.parse.Release.anime`) вторая половина не судит вовсе, и это
    не поблажка жанру, а отказ от заведомо неверного счёта. Прикидка врёт там дважды:
    делит на типовые 45 минут сериала, тогда как серия аниме идёт 24, и сравнивает с
    порогом, который писан по полнометражному кино с живой съёмкой, — а рисованная
    картинка жмётся в разы лучше, и 1-1.5 Мбит/с на серию у честного 1080p там норма.
    Пока прикидка судила, получалась ровно та бессмыслица, ради которой признак и
    заведён: пак, чьё имя серии ПЕРЕСЧИТАЛО, получал метку «старьё» за свой законный
    битрейт и топился, а сосед, чьё имя серий не считает (битрейт не вычислить), метки
    не получал и стоял верхом. Судит такую раздачу ffprobe после выбора — как и всякую,
    про которую имя молчит.

    ⚠️ Имя, которое серий не считает («Локи [S01]»), по-прежнему судится только ffprobe:
    сколько внутри файлов, до метаданных не знает никто, а делить на выдуманное число
    хуже, чем промолчать. Отбраковку это не роняет — :meth:`_Bench._trouble` читает
    настоящий кодек и выбрасывает MPEG-4 в любом случае; цена молчания — те самые
    секунды, а не подмена.

    Признак меняет только ПОРЯДОК: годность решает ffprobe, а :func:`is_candidate` его
    не спрашивает — иначе у картины, где ни в одном имени нет маркера качества, не
    осталось бы ни одного кандидата.
    """
    if release.dated:
        return True
    if release.height:  # имя назвало ступень - верим ему, спорить с ним дело ffprobe
        return release.height < HD_HEIGHT
    if release.anime:  # жанровый битрейт: 1-1.5 Мбит/с на серию - это норма, а не SD
        return False
    return 0.0 < bitrate_of(release, runtime) < SD_BITRATE


def misses_episode(release: Release, want: Episode | None) -> bool:
    """Раздача сама, своим именем, признаётся, что нужной серии в ней нет.

    Первая ступень порядка и единственная, которая стоит выше образов дисков: релиз без
    нужной серии не «хуже качеством», а бесполезен — играть в нём нечего. Молчаливое
    имя сюда не попадает никогда (:meth:`Release.covers_episode`), поэтому у сериала,
    где серии не перечисляет ни одно имя, порядок остаётся прежним.
    """
    return want is not None and not release.covers_episode(want)


def rank_releases(
    releases: list[Release],
    runtime: float,
    warn_mbit: float,
    want: Episode | None = None,
    loose: bool = False,
) -> list[Release]:
    """Порядок меню: сверху самый обсиженный кандидат, потом всё остальное по
    сидам, образы дисков всегда внизу — цельного файла внутри нет, стримить нечего.

    Первой ступенью для сериала идёт :func:`misses_episode`: раздача, которая своим
    именем говорит «нужной серии тут нет», уходит под всех, кто может её содержать, —
    даже под мёртвые и под образы дисков. Живой случай, ради которого ступень
    появилась: у «Наруто» верхом стоял ``[S01E01-08 of 220]``, у «Локи» и
    «Сверхъестественного» — такие же огрызки, а полный сезон лежал строкой ниже, и
    авто-выбор упирался в «серии s1e1 в этой раздаче нет» уже после похода в рой.

    Сразу за годностью идёт ступень :func:`is_dead`: раздача с НУЛЁМ сидов уходит под
    всех, у кого рой хоть какой-то есть. Ступень стоит выше качества нарочно: качество
    это выбор между двумя показами, а ноль сидов — это отсутствие показа, и никакой
    1080p его не перевешивает. Живой случай: у «Наруто» верхом отбора стоял
    124-гигабайтный пак с нулём сидов, а сериал на 91 сид ждал ниже, потому что
    проигрывал ему по ступени старья; старт при этом упирался в двадцатисекундное
    молчание DHT ещё до первого кадра.

    Между «живостью» и «сидами» вклинена ступень :func:`is_dated`: обсиженное
    старьё уступает место годному даже при кратной разнице в сидах. Цена вопроса
    измерена: раздача, которую ffprobe отбраковывает как ``mpeg4``, стоит 2–5 секунд
    живого старта — метаданные по DHT плюс чтение дорожек, — и это ровно те секунды,
    которые незачем держать в критическом пути. На «Моане 2» так и было: первым
    кандидатом стоял 1.46-гигабайтный .avi с 221 сидом, а годный WEB-DL-AVC с 140
    сидами ждал своей очереди вторым.

    Следом за ней — ступень :func:`sound_step`: звук, которого не понять, — это не
    «качество похуже», а несмотренный тайтл. Поэтому она стоит ВЫШЕ :func:`is_full_hd`:
    обе ступени размениваются на сиды, и размен «1080p вместо 720p» дешевле размена
    «по-русски вместо по-японски». Ниже :func:`is_dated` она стоит по обратной причине:
    русский .avi вместо честного 1080p — это уже не размен, а откат по всему фронту.

    Следом — ступень :func:`is_full_hd`: живой 1080p обходит 720p, даже когда сидов
    у него меньше. Дальше внутри каждой группы всё как было — сиды, потом размер.

    ``loose`` — ворота отбора открыты (:func:`gate_open`), и молчаливые имена идут
    в кандидатах наравне с именными.
    """
    alive = max((r.seeders for r in releases), default=0)
    return sorted(
        releases,
        key=lambda r: (
            misses_episode(r, want),
            is_disc(r),
            not is_candidate(r, runtime, warn_mbit, loose),
            is_dead(r, alive),
            is_dated(r, runtime),
            sound_step(r, alive),
            not is_full_hd(r, alive),
            -r.seeders,
            -r.size,
        ),
    )


def is_dead(release: Release, alive: int) -> bool:
    """Ноль сидов при живых соседях: играть тут нечего ни на каком качестве.

    Живость участвовала в порядке и раньше, но только ВНУТРИ ступеней качества
    (:func:`is_full_hd`, :func:`sound_step`) — то есть мёртвая раздача имела полное
    право стоять верхом, если по имени она годнее живой. Так и было на живой выдаче
    «наруто»: 124-гигабайтный пак с нулём сидов обходил сериал на 91 сид, потому что у
    того в имени стоит ``DVDRip``. Enter в такой верх — это двадцать секунд молчания
    DHT и переход к следующему, то есть чистая потеря старта.

    Порог тут ровно ноль, и никакой доли от лидера: доля — это размен «поменьше сидов
    ради ступени качества», и её уже держат :data:`FULL_HD_LIVENESS` и
    :data:`SOUND_LIVENESS`, каждый со своей ценой. А ноль — не размен: раздача,
    которую никто не раздаёт, не играется вовсе.

    ``alive`` — сиды лидера пула. Пул, где на нуле ВСЕ (свежая раздача, индексер не
    отдал числа), ступень не трогает: понижать там некого и не в пользу кого.
    """
    return alive > 0 and release.seeders <= 0


def is_full_hd(release: Release, alive: int) -> bool:
    """Имя обещает 1080p (или выше), и раздача при этом жива.

    Ступень нужна затем, что до неё разрешение в порядке не участвовало вовсе: среди
    кандидатов правили одни сиды, и названный 1080p проигрывал названному 720p с
    троекратным перевесом сидов. На «Мастере и Маргарите» так и было — верхом стоял
    ``WEB-DL 720p`` со 146 сидами, а ``WEB-DL 1080p`` с 59 ждал вторым.

    Живость в условии не для красоты, и цена у неё замерена на той же выдаче: у «Зелёной
    мили» единственные названные 1080p имеют 4 и 1 сид против 38 у 720p, у «Форреста
    Гампа» — 2, 1, 0, 0 против 41. Поднять такой 1080p значило бы поменять ступень
    качества на подгрузы, а гейт показа прямо обратный: плавность выше пиковой чёткости.
    Порог :data:`FULL_HD_LIVENESS` разводит эти случаи с запасом — 0.40 против 0.10 и 0.05.

    Врущему имени ступень не помогает: подтверждает разрешение ffprobe, и «названный
    1080p, а внутри 574p» подменяется на честного соседа (:meth:`_Bench._honest`).

    2160p поднимается вместе с 1080p: это тоже честный HD, а его тяжесть снимает
    перекодирование на ходу — отбраковывает только ``bitrate_hard_mbit``.
    """
    if release.height < FULL_HEIGHT or release.seeders <= 0:
        return False
    return release.seeders >= alive * FULL_HD_LIVENESS


def bitrate_of(release: Release, duration: float) -> float:
    """Оценка битрейта по размеру раздачи. У фильма делится вся раздача, у сериала —
    размер ОДНОЙ СЕРИИ: «9.7 ГБ» на восемь серий это 3 Мбит/с, а не 30, и по оценке
    целиком самые обсиженные раздачи сезона улетали бы вниз с пометкой «тяжёлый».

    Сколько внутри серий, говорит имя раздачи (:attr:`Release.episode_count`):
    ``[S01E01-08 of 220]`` — восемь, ``[E220 of 220]`` — двести двадцать. Имя молчит —
    отдаём ноль, как и раньше: делить на выдуманный счёт значит врать себе, а
    настоящий битрейт серии всё равно померит ffprobe по её файлу.
    """
    if release.kind != "tv":
        return bitrate_mbit(release.size, duration)
    count = release.episode_count
    return bitrate_mbit(release.size // count, duration) if count else 0.0


def render_table(
    releases: list[Release],
    runtime: float,
    warn_mbit: float,
    limit: int = TABLE_LIMIT,
    recode_at: float = 0.0,
) -> str:
    """Таблица релизов: N · качество · размер · сиды · озвучка · кодек. Битрейт для
    пометки прикидывается по размеру и типовой длительности, пока настоящая не прочитана
    ffprobe; ниже ``limit`` — раздачи без сидов, выбирать там нечего.
    """
    shown = releases[:limit]
    rows = [
        (
            str(number),
            r.quality or "?",
            _gb(r.size),
            str(r.seeders),
            _cut(", ".join(r.voices) or "-", 34),
            ((r.codec or "?") + " " + warned(r, runtime, warn_mbit, recode_at)).strip(),
        )
        for number, r in enumerate(shown, start=1)
    ]
    head = ("N", "Качество", "Размер", "Сиды", "Озвучка", "Кодек")
    width = [max(len(c[i]) for c in (head, *rows)) for i in range(len(head))]

    def line(cells: tuple[str, ...]) -> str:
        return "  " + "  ".join(_pad(c, w) for c, w in zip(cells, width, strict=True))

    out = ["Релизы:", line(head), *(line(row).rstrip() for row in rows)]
    if len(releases) > len(shown):
        out.append(f"  ... и ещё {len(releases) - len(shown)} с меньшим числом сидов")
    return "\n".join(out)


def pick_voice(media: Media, args: Args, remembered: str = "") -> tuple[int, str]:
    """Какую дорожку играем и что после этого лежит в памяти картины.

    **На счастливом пути вопроса про озвучку нет.** Дорожка выбирается сама
    (:meth:`Media.default_track`), и её подпись печатается в строке запуска —
    молчаливых подмен не бывает.

    Спросить можно только явно: ``--voice N`` берёт дорожку N, ``--voice`` без номера
    показывает меню. Оба — явный выбор, и только он пишется в память картины
    (:attr:`torrcast.state.Entry.voice`). Автовыбор память не трогает: иначе первый же
    запуск с другим релизом переписал бы то, что пользователь выбрал руками.

    Возвращает пару «номер дорожки в этом релизе, память картины».
    """
    if not media.tracks:
        raise InfraError("в файле нет звуковых дорожек")
    if args.voice is not None:
        index = _ask_voice(media) if args.voice == VOICE_MENU else _voice_number(media, args.voice)
        return index, media.tracks[index].label
    if remembered:
        found = media.find_voice(remembered)
        if found is not None:
            return found, remembered
        # Память живёт на картину, а релиз временный: озвучки в нём нет - говорим и
        # играем обычную, но выбор пользователя не забываем (:attr:`Entry.voice`).
        print(f"озвучки «{remembered}» в этом релизе нет - беру обычную")
    return media.default_track(), remembered


#: Языковые коды ffprobe → как язык зовут вслух. Список короткий и ровно про то, что
#: живёт в раздачах кино и аниме; чего в нём нет, называется «оригинальный».
_SPOKEN: dict[str, str] = {
    "jpn": "японский",
    "ja": "японский",
    "jap": "японский",
    "eng": "английский",
    "en": "английский",
    "kor": "корейский",
    "zho": "китайский",
    "chi": "китайский",
    "fra": "французский",
    "fre": "французский",
    "deu": "немецкий",
    "ger": "немецкий",
    "spa": "испанский",
    "ita": "итальянский",
}


def spoken(track: AudioTrack) -> str:
    """Как назвать язык дорожки вслух: «японский»; неизвестный — «оригинальный»."""
    return _SPOKEN.get((track.language or "").strip().casefold(), "оригинальный")


def sound_note(
    media: Media, audio: int, pool: list[Release], release: Release | None = None
) -> str:
    """Честная строка про звук, когда русской дорожки в файле не оказалось; иначе пусто.

    Решение владельца по аниме: субтитров не делаем — значит японский тайтл без
    перевода останется японским, и показ обязан сказать это ДО картинки, а не оставить
    человека выяснять на слух. Показ при этом играет: решает он сам, наше дело —
    предупредить честно.

    Строки две, и разница между ними не косметическая:

    * перевода нет вообще ни у кого в выдаче — «только японский звук, перевода в
      каталоге нет», и делать тут больше нечего;
    * перевод в каталоге есть, но в этом релизе его не оказалось — такое бывает
      у ``RUS(ext)``, где русская дорожка лежит отдельным файлом, — тогда строка
      называет и запасной ход: выбрать раздачу руками.

    Чей звук играет, читается из дорожки (:func:`spoken`), а не додумывается: у
    французского фильма без перевода японского звука взяться неоткуда.
    """
    if not media.tracks or any(t.is_russian for t in media.tracks):
        return ""
    track = media.tracks[audio] if audio < len(media.tracks) else media.tracks[0]
    if not track.named:
        # Раздача язык дорожки не назвала (тег ``und``). Единственная косвенная улика -
        # имя раздачи: русский маркер в нём (:attr:`Release.dubbed`) - повод СКАЗАТЬ про
        # русскую, назвав источник, а не молча подставить её (и не выдать за неё). Улики
        # нет - язык так и остаётся неизвестным, и об этом честная строка.
        if release is not None and release.dubbed:
            return "звук без метки языка - по имени релиза русская"
        return "язык дорожки неизвестен - раздача не назвала язык озвучки"
    lang = spoken(track)
    if any(r.dubbed and r.seeders > 0 for r in pool):
        return (
            f"только {lang} звук - перевода в этом релизе нет, но в каталоге он есть: "
            "cast releases <запрос>, потом cast <запрос> --release N"
        )
    return f"только {lang} звук, перевода в каталоге нет"


def _voice_number(media: Media, number: int) -> int:
    """Номер дорожки от человека → индекс; чужого номера нет — честная строка."""
    if not 1 <= number <= len(media.tracks):
        raise NotFoundError(
            f"дорожек {len(media.tracks)}, номера {number} нет - посмотри: cast voices <запрос>"
        )
    return number - 1


def _ask_voice(media: Media) -> int:
    """Меню озвучек — только по ``--voice`` без номера. Дефолт тот же, что и без флага."""
    default = media.default_track()
    if len(media.tracks) == 1:  # выбора нет - вопроса тоже
        return default
    print(voices_table(media, default))
    return ask("Озвучка?", len(media.tracks), default=default + 1) - 1


def voices_table(media: Media, default: int, remembered: str = "") -> str:
    """Список озвучек с пометками «дефолт» и «запомнено» — для меню и ``cast voices``."""
    found = media.find_voice(remembered) if remembered else None
    rows = []
    for track in media.tracks:
        marks = (("дефолт", track.index == default), ("запомнено", track.index == found))
        note = [word for word, on in marks if on]
        tail = f"   [{', '.join(note)}]" if note else ""
        rows.append(f"  {track.index + 1}. {track.label}{tail}")
    return "\n".join(["Озвучка:", *rows])


def _gb(size: int) -> str:
    return f"{size / 1024**3:.1f} ГБ" if size else "-"


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _pad(text: str, width: int) -> str:
    return text + " " * (width - len(text))


def _hms(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


if __name__ == "__main__":
    raise SystemExit(main())
