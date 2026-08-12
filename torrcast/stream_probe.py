"""Часть медиатракта; публичный фасад — :mod:`torrcast.stream`."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.stream_core import _SEGMENT_RE as _SEGMENT_RE
    from torrcast.stream_core import HEAD_WARM as HEAD_WARM
    from torrcast.stream_core import META_GRACE as META_GRACE
    from torrcast.stream_core import PROBE_KEPT as PROBE_KEPT
    from torrcast.stream_core import WARM_TIMEOUT as WARM_TIMEOUT
    from torrcast.stream_core import AudioTrack as AudioTrack
    from torrcast.stream_core import ContactWait as ContactWait
    from torrcast.stream_core import Media as Media
    from torrcast.stream_core import TorrFile as TorrFile
    from torrcast.stream_core import TorrServer as TorrServer
    from torrcast.stream_serve import _opt_str as _opt_str


import contextlib
import hashlib
import json
import os
import subprocess
import threading
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from torrcast import InfraError, NotFoundError, SwarmError
from torrcast.parse import VIDEO_EXT

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class Supply:
    """Источник показа: служба раздач и НАША раздача в ней. Спрашивают его на краю показа.

    🔴 Обрыв входа показ и раньше переживал, но объяснить его не мог: упаковка умирает
    одинаково и когда просел рой, и когда службы раздач не стало вовсе. Разница между
    этими двумя случаями - вся разница для человека: в первом ждать бессмысленно, во
    втором показ поднимется сам. Замерено на перезапуске службы под показом: показ гас за
    3.5-12 с, человек 14 с не видел ни строки, а потом получал «приёмник не досмотрел
    поток» - обвинение приёмника, который ни в чём не виноват. Спросить источник стоит
    двух запросов и делается это ровно там, где показ уже кончается.

    ⚠️ В горячем пути этих вопросов быть не должно: раздача сегментов не ждёт ни журнал,
    ни лишний запрос. Поэтому :meth:`trouble` зовут только два места, и оба - край показа:
    упаковка объявила себя мёртвой и приёмник погасил экран.

    Второе назначение - :meth:`restore`. Раздачу после аварии возвращает МАГНИТ, потому
    что в URL потока едет только хэш (:meth:`TorrServer.stream_url`), а служба, заведя
    раздачу по голому хэшу, остаётся без трекеров: замерено - 25 с и ноль байт.
    """

    #: Клиент службы. Свой, а не общий с показом: вопросы задаются из сторожа, а коротким
    #: сроком (:data:`PROBE_TIMEOUT`) мёртвая служба отличается от живой сразу.
    server: TorrServer
    #: Хэш НАШЕЙ раздачи. Всё, что делает :class:`Supply`, делается по нему и только по
    #: нему: чужие раздачи в службе не наше дело - ни считать, ни убирать.
    torrent_hash: str = ""
    #: Магнит той же раздачи - из записи картины. Трекеры живут здесь и больше нигде.
    magnet: str = ""
    #: Последняя замеченная авария источника; пусто - аварии не было или её уже разгребли.
    #: По нему же :meth:`check` знает, что раздачу надо вернуть магнитом, даже если она
    #: уже числится в списке: заведённая по голому хэшу, она числится там точно так же.
    lost: str = ""
    #: Правда ли последняя проверка вернула раздачу магнитом. Об этом говорят вслух - и
    #: человеку, и следу, - потому что это и есть возврат трекеров.
    restored: bool = False
    #: Монотонный момент последнего возврата: от него отсчитывается :data:`META_GRACE`.
    restored_at: float = 0.0

    def check(self) -> str:
        """Что не так с ИСТОЧНИКОМ прямо сейчас; пусто - источник в порядке.

        Три вопроса по нарастающей, и каждый отвечает за свой вид аварии: служба не
        отвечает вовсе; служба жива, но нашей раздачи в ней нет (перезапуск: раздачи мы
        заводим с ``save_to_db:false``, и после него список пуст); раздача есть, а
        метаданных у неё нет - это она и есть, заведённая по голому хэшу из нашего же URL
        потока, без трекеров.

        Заметив, что служба вернулась, метод тут же возвращает ей раздачу МАГНИТОМ
        (:meth:`_restore`) - и только после этого говорит, что источник в порядке. Иначе
        «в порядке» было бы враньём: раздача без трекеров ищет пиров одним DHT и за 25 с
        не приносит ни байта (замерено).
        """
        self.restored = False
        if not self.torrent_hash:
            return ""
        try:
            if not self.server.alive():
                return self._blame("TorrServer не отвечает")
            if not self.server.listed(self.torrent_hash):
                self._blame("TorrServer потерял нашу раздачу")
            elif not self.server.files(self.torrent_hash):
                if time.monotonic() - self.restored_at < META_GRACE:
                    return ""  # раздачу только что вернули магнитом - метаданные ещё едут
                self._blame("раздача осталась без трекеров - метаданных нет")
            elif not self.lost:
                return ""  # служба отвечает, раздача на месте, аварии за ней не числится
        except InfraError as exc:
            return self._blame(str(exc))
        return self._restore()

    def _restore(self) -> str:
        """Вернуть раздачу магнитом; пусто - вернули (или возвращать было нечего).

        Идемпотентно и у нас, и у службы: infohash тот же, значит и раздача та же - дубля
        не заводится, а трекеры из магнита к ней возвращаются. Чужих раздач это не
        касается никак: всё, что делает :class:`Supply`, делается по нашему хэшу.

        ⚠️ Магнит берётся из записи картины и ниоткуда больше: ходить за ним в индексеры
        посреди аварии было бы вторым способом не показать кино.
        """
        why_source = self.lost
        if not self.magnet:
            return why_source  # магнита нет - вернуть раздачу нечем, врать не о чем
        try:
            self.server.add(self.magnet)
        except InfraError:
            return why_source or "TorrServer не отвечает"  # служба ещё не поднялась
        self.lost, self.restored, self.restored_at = "", True, time.monotonic()
        return ""

    def _blame(self, why_source: str) -> str:
        self.lost = why_source
        return why_source


def _touch(cache: Path) -> None:
    """Отметить, что кэшем только что воспользовались.

    Полки живут по времени **обращения**, а не создания (:func:`_trim`): карта фильма,
    который смотрят каждый вечер, снимается один раз, и вытеснять её за возраст значило
    бы выбрасывать ровно то, что нужнее всего. ``utime`` - одна запись в inode, файл при
    этом не читается и не переписывается.
    """
    with contextlib.suppress(OSError):
        os.utime(cache)


def _mtime(entry: os.DirEntry[str]) -> float:
    with contextlib.suppress(OSError):
        return entry.stat().st_mtime
    return 0.0


def _trim(directory: Path, kept: int) -> None:
    """Подрезать полку до ``kept`` самых недавно спрошенных. Осечка - не беда: это кэш.

    Подрезка идёт в общей нитке с показом, поэтому она дважды скупая. Имена берутся одним
    ``scandir``, а времена спрашиваются только когда потолок и правда перебран - и тогда
    режем сразу до трёх четвертей полки. Иначе на полной полке полный обход с ``stat``
    приходился бы на каждый старт; так он приходится раз на четверть потолка, то есть
    раз на 64 новых карты, а потолок остаётся потолком.

    Цена замерена на полке в 256 карт с живым разбросом весов: обычный старт - 0.18 мс
    (максимум 0.46), тот один старт из 64, где подрезка срабатывает, - 4.25 мс
    (максимум 8.55). Против секунд ожидания роя это ноль.

    Того, что смотрят прямо сейчас, подрезка не касается: его запись либо только что
    сделана (значит, самая свежая), либо только что прочитана и отмечена
    (:func:`_touch`). Чтобы такая запись попала под нож, между её чтением и подрезкой
    должны появиться десятки более свежих - а это уже не «сейчас».

    Берутся только ``*.json``: черновики и замки соседних писателей - не наше дело.
    """
    with contextlib.suppress(OSError):
        with os.scandir(directory) as reading:
            shelf = [entry for entry in reading if entry.name.endswith(".json")]
        if len(shelf) <= kept:
            return
        for entry in sorted(shelf, key=_mtime)[: len(shelf) - kept * 3 // 4]:
            with contextlib.suppress(OSError):
                Path(entry.path).unlink(missing_ok=True)


def shelf_weight(directory: Path) -> tuple[int, int]:
    """Сколько на полке записей и сколько они весят байт; нет полки - ``(0, 0)``.

    Нужно одному ``cast doctor``: кэши тихо растут годами, и цифра рядом с потолком -
    единственный способ заметить это раньше, чем кончится место.
    """
    count = 0
    weight = 0
    with contextlib.suppress(OSError), os.scandir(directory) as reading:
        for entry in reading:
            if not entry.name.endswith(".json"):
                continue
            count += 1
            with contextlib.suppress(OSError):
                weight += entry.stat().st_size
    return count, weight


#: Версия формата паспорта на полке (:func:`_read_media`). Растёт, когда в паспорт
#: добавляется поле, от которого зависит РЕШЕНИЕ показа: старая запись такого поля не
#: несёт, и молчание в ней неотличимо от честного ответа. ``2`` - формат кадра и профиль,
#: ``3`` - кривая яркости (:attr:`Media.hdr`), ``4`` - развёртка (:attr:`Media.interlaced`).
_MEDIA_VERSION: Final = 4


def _media_cache(source_url: str) -> Path:
    """Где лежит снятый паспорт этого файла (:func:`probe`).

    Ключ тот же, что у карты опорных кадров (:func:`_keys_cache`), и по той же причине:
    в URL потока лежат hash раздачи и номер файла, то есть ровно то, что определяет
    содержимое. Меняться паспорту негде: длительность, дорожки и кодек - это сам файл.
    """
    from torrcast.state import state_path

    return (
        state_path().parent / "probe" / f"{hashlib.sha1(source_url.encode()).hexdigest()[:16]}.json"
    )


def _read_media(cache: Path) -> Media | None:
    """Паспорт с полки; ``None`` - полки нет, запись битая или снята прежней версией.

    ⚠️ Версия проверяется, и это не бюрократия. Паспорта прежних версий не несут формата
    кадра, то есть про десятибитный H.264 молчат ровно так же, как молчал старый ffprobe:
    прими мы такой паспорт за правду - и показ снова уехал бы копией на приёмник, который
    её не декодирует (:func:`recodes_whole`). Цена отказа - один ffprobe на файл, один
    раз; цена доверия - вечная петля на экране.
    """
    with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
        saved = json.loads(cache.read_text("utf-8"))
        if int(saved.get("v") or 0) < _MEDIA_VERSION:
            return None
        media = Media(
            duration=float(saved["duration"]),
            tracks=tuple(AudioTrack(**track) for track in saved["tracks"]),
            video=_opt_str(saved.get("video")),
            profile=_opt_str(saved.get("profile")),
            pix_fmt=_opt_str(saved.get("pix_fmt")),
            color_trc=_opt_str(saved.get("color_trc")),
            field_order=_opt_str(saved.get("field_order")),
            height=int(saved.get("height") or 0),
            width=int(saved.get("width") or 0),
            video_bps=float(saved.get("video_bps") or 0.0),
        )
        _touch(cache)  # полка живёт по времени обращения (:func:`_trim`)
        return media
    return None


def _keep_media(cache: Path, media: Media) -> None:
    """Положить паспорт в кэш. Осечка записи молча игнорируется: кэш - ускорение, а не
    источник правды, и показ обязан идти и без него."""
    if media.duration <= 0 or not media.tracks:
        # Паспорт без длительности и дорожек - это не паспорт, а недочитанный заголовок:
        # такой в кэш класть нельзя, иначе осечка одного запуска станет вечной.
        return
    with contextlib.suppress(OSError, TypeError, ValueError):
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(f".{os.getpid()}-{threading.get_ident()}.tmp")
        tmp.write_text(
            json.dumps(
                {
                    "v": _MEDIA_VERSION,
                    "duration": media.duration,
                    "tracks": [asdict(track) for track in media.tracks],
                    "video": media.video,
                    "profile": media.profile,
                    "pix_fmt": media.pix_fmt,
                    "color_trc": media.color_trc,
                    "field_order": media.field_order,
                    "height": media.height,
                    "width": media.width,
                    "video_bps": media.video_bps,
                }
            ),
            encoding="utf-8",
        )
        tmp.replace(cache)
    _trim(cache.parent, PROBE_KEPT)


def _run_ffprobe(command: list[str], timeout: float, alive: Any) -> str:
    """Запустить ffprobe и вернуть stdout. Без ``alive`` — прежний :func:`subprocess.run`
    с тем же таймаутом; с ``alive`` — то же самое, но с возможностью оборвать чтение
    раньше бюджета, когда рой замолчал (:func:`swarm_pulse`).

    Живой релиз проходит ровно как раньше: ffprobe дочитывает заголовок и выходит сам,
    ``alive`` всё это время True, никакой лишней секунды не добавляется. Обрыв случается
    только на молчащем рое — там, где иначе сгорел бы весь ``timeout``.
    """
    if alive is None:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=True)
        return done.stdout
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            out, err = proc.communicate(timeout=0.5)
        except subprocess.TimeoutExpired:
            if not alive():
                proc.kill()
                proc.communicate()
                raise SwarmError("рой молчит - за отсрочку не пришло ни байта потока") from None
            if time.monotonic() >= deadline:
                proc.kill()
                proc.communicate()
                raise subprocess.TimeoutExpired(command, timeout) from None
            continue
        if proc.returncode:
            raise subprocess.CalledProcessError(proc.returncode, command, out, err)
        return out


def swarm_pulse(
    source_url: str, grace: float, wait: ContactWait | None = None
) -> Callable[[], bool]:
    """Признак жизни потока под ffprobe: тянет первые байты в фоне и отвечает, стоит ли
    ещё ждать. Пришёл хоть байт — раздача жива и читается (у «Моаны 2» заголовок едет
    17 с, это норма, и обрывать её нельзя). Ни байта за ``grace`` — рой молчит: пиров
    нет, и досиживать на нём весь :data:`torrcast.cli.PROBE_BUDGET` незачем, запасной уже
    греется параллельно (:meth:`torrcast.cli._Bench.resolve`).

    Читаем ровно до первого куска: подтвердить жизнь достаточно, а сами байты в кэш роя
    тянут прогрев (:func:`warm_file`) и показ — второй раз их брать незачем.
    """
    started = time.monotonic()
    seen = threading.Event()

    def pull() -> None:
        request = urllib.request.Request(source_url, headers={"Range": f"bytes=0-{HEAD_WARM - 1}"})
        with (
            contextlib.suppress(Exception),
            urllib.request.urlopen(request, timeout=WARM_TIMEOUT) as answer,
        ):
            if answer.read(1 << 20):
                seen.set()

    threading.Thread(target=pull, daemon=True).start()

    def alive() -> bool:
        began = wait.activated_at if wait is not None else started
        return seen.is_set() or began is None or (time.monotonic() - began) < grace

    return alive


def probe(url: str, timeout: float = 90.0, alive: Any = None) -> Media:
    """Дорожки и длительность из HTTP-потока, не качая файл: ffprobe берёт заголовок mkv
    запросами Range — это и есть цена меню озвучек.

    Паспорт кэшируется на диск (:func:`_media_cache`) по тем же причинам, что и карта
    опорных кадров: содержимое файла задано раздачей и номером файла, а первое чтение
    стоит роя - до 17 с на «Моане 2». Но время тут даже не главное. Следующая серия
    узнаёт свою длительность именно отсюда (:func:`torrcast.cli._duration`), а узнать её
    она обязана и тогда, когда сети уже нет: без длительности нет ни порога 95 %, ни
    сетки, ни манифеста - то есть нет и автоперехода на прогретую серию посреди обрыва.

    ``alive`` — жив ли смысл дочитывать. Раздача с мёртвым роем метаданные отдаёт (они
    уже в TorrServer), а содержимого не отдаёт вовсе: ffprobe на ней молча сидит весь
    ``timeout``. Признак жизни (:func:`swarm_pulse`) отличает такую от честно долгого
    заголовка и даёт оборвать ожидание рано, не жгя весь бюджет на молчащем релизе.
    """
    cache = _media_cache(url)
    if (ready := _read_media(cache)) is not None:
        return ready
    entries = (
        "format=duration:"
        # ``profile`` и ``pix_fmt`` берутся тем же одним запросом и ничего не стоят, а без
        # них показ не отличает Hi10P от обычного H.264 (:func:`recodes_whole`).
        "stream=index,codec_name,codec_type,channels,width,height,bit_rate,profile,pix_fmt,"
        # ``color_transfer`` - оттуда же и даром, а без него HDR не отличить от SDR вовсе.
        # ``field_order`` - единственное место, откуда видна развёртка самого файла:
        # имя раздачи про неё молчит или врёт, а гребёнку на экране даёт поток.
        "color_transfer,field_order:"
        # Теги дорожки берутся ЦЕЛИКОМ, а не списком: mkvmerge пишет вес дорожки то как
        # ``BPS``, то как ``BPS-eng``/``BPS-rus`` - суффикс языковой и заранее неизвестен.
        "stream_tags"
    )
    flags = ["-v", "error", "-show_entries", entries, "-of", "json"]
    command = ["ffprobe", *flags, url]
    try:
        stdout = _run_ffprobe(command, timeout, alive)
    except FileNotFoundError as exc:
        raise InfraError("ffprobe не установлен") from exc
    except subprocess.TimeoutExpired as exc:
        raise InfraError("ffprobe не дождался потока") from exc
    except subprocess.CalledProcessError as exc:
        raise InfraError(f"ffprobe не прочитал поток: {(exc.stderr or '').strip()[:120]}") from exc
    try:
        payload: Any = json.loads(stdout)
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
    media = Media(
        duration=duration,
        tracks=tuple(_track(i, s) for i, s in enumerate(audio)),
        video=_opt_str(video[0].get("codec_name")) if video else None,
        profile=_opt_str(video[0].get("profile")) if video else None,
        pix_fmt=_opt_str(video[0].get("pix_fmt")) if video else None,
        color_trc=_opt_str(video[0].get("color_transfer")) if video else None,
        field_order=_opt_str(video[0].get("field_order")) if video else None,
        height=int(video[0].get("height") or 0) if video else 0,
        width=int(video[0].get("width") or 0) if video else 0,
        video_bps=_video_bps(video[0], duration) if video else 0.0,
    )
    _keep_media(cache, media)
    return media


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
    """Самый крупный видеофайл раздачи, он же фильм; образ диска — :class:`NotFoundError`.

    Тип отказа здесь - не украшение, а решение отбора (:func:`torrcast.cli._silenced`):
    :class:`InfraError` - это «рой промолчал, про раздачу не узнали ничего», и такую
    раздачу промолчавшая очередь спрашивает ещё раз. А тут метаданные приехали целиком
    и ответ известен навсегда: видеофайла в раздаче нет. Второй спрос дал бы ровно тот
    же ответ за те же секунды - как у «нужной серии в раздаче нет»
    (:meth:`torrcast.cli._Series.choose`), и тип у них один.
    """
    videos = [f for f in files if f.name.lower().endswith(VIDEO_EXT)]
    if not videos:
        raise NotFoundError(
            "в раздаче нет отдельного видеофайла (похоже на образ диска) - "
            "возьми другой релиз: cast <запрос> --release N"
        )
    return max(videos, key=lambda f: f.size)


def segment_name(slot: int) -> str:
    """Имя файла сегмента. Имя = место в фильме, а не номер по порядку упаковки — это и
    делает возможным манифест на весь фильм при упаковке по требованию.
    """
    return f"v{slot}.ts"


def segment_slot(name: str) -> int:
    """Слот по имени файла; ``-1`` — имя не наше."""
    found = _SEGMENT_RE.fullmatch(name)
    return int(found.group(1)) if found else -1


